import asyncio
import importlib.util
import sys
import types
import unittest
from contextlib import contextmanager
from pathlib import Path


PROPAGATED_ATTRIBUTES = {}


@contextmanager
def fake_propagate_attributes(**attributes):
    global PROPAGATED_ATTRIBUTES
    previous = PROPAGATED_ATTRIBUTES
    PROPAGATED_ATTRIBUTES = attributes
    try:
        yield
    finally:
        PROPAGATED_ATTRIBUTES = previous


class FakeObservation:
    def __init__(self, *, parent=None, trace_id=None, **kwargs):
        self.parent = parent
        self.trace_id = trace_id if trace_id else parent.trace_id
        self.kwargs = kwargs
        self.propagated_attributes = dict(PROPAGATED_ATTRIBUTES)
        self.children = []
        self.updates = []
        self.ended = False

    def start_observation(self, **kwargs):
        child = FakeObservation(parent=self, **kwargs)
        self.children.append(child)
        return child

    def update(self, **kwargs):
        self.updates.append(kwargs)
        return self

    def end(self):
        self.ended = True
        return self


class FakeLangfuse:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.roots = []
        self.flush_count = 0

    def auth_check(self):
        return True

    def create_trace_id(self, *, seed):
        return f"trace-{seed}"

    def start_observation(self, *, trace_context, **kwargs):
        root = FakeObservation(trace_id=trace_context["trace_id"], **kwargs)
        self.roots.append(root)
        return root

    def flush(self):
        self.flush_count += 1


class FakeBaseModel:
    def __init__(self, **kwargs):
        for name, value in self.__class__.__dict__.items():
            if not name.startswith("_") and not callable(value):
                setattr(self, name, value)
        for name, value in kwargs.items():
            setattr(self, name, value)


def fake_field(*, default_factory):
    return default_factory()


def load_pipeline_module():
    langfuse_module = types.ModuleType("langfuse")
    langfuse_module.Langfuse = FakeLangfuse
    langfuse_module.propagate_attributes = fake_propagate_attributes
    pydantic_module = types.ModuleType("pydantic")
    pydantic_module.BaseModel = FakeBaseModel
    pydantic_module.Field = fake_field
    utils_module = types.ModuleType("utils")
    pipelines_module = types.ModuleType("utils.pipelines")
    main_module = types.ModuleType("utils.pipelines.main")
    main_module.get_last_assistant_message = lambda messages: next(
        (
            message.get("content")
            for message in reversed(messages)
            if message["role"] == "assistant"
        ),
        None,
    )

    replacements = {
        "langfuse": langfuse_module,
        "pydantic": pydantic_module,
        "utils": utils_module,
        "utils.pipelines": pipelines_module,
        "utils.pipelines.main": main_module,
    }
    previous = {name: sys.modules.get(name) for name in replacements}
    sys.modules.update(replacements)
    try:
        path = (
            Path(__file__).parents[1]
            / "examples"
            / "filters"
            / "langfuse_v4_filter_pipeline.py"
        )
        spec = importlib.util.spec_from_file_location("langfuse_v4_pipeline", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, old_module in previous.items():
            if old_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old_module


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.module = load_pipeline_module()
        self.pipeline = self.module.Pipeline()
        self.pipeline.set_langfuse()
        self.body = {
            "model": "model-id",
            "messages": [{"role": "user", "content": "Hello"}],
            "metadata": {
                "chat_id": "chat-123",
                "task": "custom-task",
                "model": {"name": "Friendly Model"},
            },
        }
        self.user = {"email": "user@example.com"}

    def test_inlet_and_outlet_create_parented_v4_observations(self):
        asyncio.run(self.pipeline.inlet(self.body, self.user))
        root = self.pipeline.chat_traces["chat-123"]
        user_event = root.children[0]

        self.assertEqual(root.trace_id, "trace-chat-123")
        self.assertEqual(user_event.parent, root)
        self.assertEqual(user_event.kwargs["as_type"], "span")
        self.assertTrue(user_event.ended)
        for observation in (root, user_event):
            self.assertEqual(
                observation.propagated_attributes["user_id"], "user@example.com"
            )
            self.assertEqual(
                observation.propagated_attributes["session_id"], "chat-123"
            )
            self.assertEqual(
                observation.propagated_attributes["tags"],
                ["open-webui", "custom-task"],
            )

        self.body["messages"].append(
            {
                "role": "assistant",
                "content": "Hi!",
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            }
        )
        asyncio.run(self.pipeline.outlet(self.body, self.user))
        generation = root.children[1]

        self.assertEqual(generation.parent, root)
        self.assertEqual(generation.kwargs["as_type"], "generation")
        self.assertEqual(generation.kwargs["model"], "model-id")
        self.assertEqual(generation.kwargs["usage_details"], {"input": 7, "output": 3})
        self.assertNotIn("usage", generation.kwargs)
        self.assertEqual(generation.propagated_attributes["session_id"], "chat-123")
        self.assertEqual(
            generation.propagated_attributes["user_id"], "user@example.com"
        )
        self.assertEqual(
            generation.propagated_attributes["tags"],
            ["open-webui", "custom-task"],
        )
        self.assertTrue(generation.ended)
        self.assertTrue(root.ended)
        self.assertNotIn("chat-123", self.pipeline.chat_traces)
        self.assertEqual(self.pipeline.langfuse.flush_count, 1)

    def test_turns_share_a_trace_id_without_leaking_roots(self):
        trace_ids = []
        for _ in range(2):
            body = {
                "model": "model-id",
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi!"},
                ],
                "metadata": {"chat_id": "chat-123"},
            }
            asyncio.run(self.pipeline.inlet(body, self.user))
            root = self.pipeline.chat_traces["chat-123"]
            trace_ids.append(root.trace_id)
            asyncio.run(self.pipeline.outlet(body, self.user))
            self.assertTrue(root.ended)

        self.assertEqual(trace_ids, ["trace-chat-123", "trace-chat-123"])
        self.assertFalse(self.pipeline.chat_traces)

    def test_shutdown_closes_unfinished_turns_and_flushes(self):
        asyncio.run(self.pipeline.inlet(self.body, self.user))
        root = self.pipeline.chat_traces["chat-123"]
        asyncio.run(self.pipeline.on_shutdown())

        self.assertTrue(root.ended)
        self.assertFalse(self.pipeline.chat_traces)
        self.assertFalse(self.pipeline.model_names)
        self.assertEqual(self.pipeline.langfuse.flush_count, 1)

    def test_inlet_rejects_missing_required_keys(self):
        with self.assertRaisesRegex(ValueError, "Missing keys.*model"):
            asyncio.run(self.pipeline.inlet({"messages": []}, self.user))

    def test_requirement_constraint_survives_pipeline_frontmatter_parsing(self):
        source = (
            Path(__file__).parents[1]
            / "examples"
            / "filters"
            / "langfuse_v4_filter_pipeline.py"
        ).read_text()
        requirement = next(
            line.removeprefix("requirements: ")
            for line in source.splitlines()
            if line.startswith("requirements: ")
        )

        self.assertEqual(requirement, "langfuse~=4.7")
        self.assertEqual(requirement.split(","), ["langfuse~=4.7"])


if __name__ == "__main__":
    unittest.main()
