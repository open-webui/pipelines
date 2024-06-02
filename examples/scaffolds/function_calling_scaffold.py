from blueprints.function_calling_blueprint import Pipeline as FunctionCallingBlueprint


class Pipeline(FunctionCallingBlueprint):
    class Valves(FunctionCallingBlueprint.Valves):
        # Add your custom valves here
        pass

    class Tools:
        def __init__(self, pipeline) -> None:
            self.pipeline = pipeline

        # Add your custom tools using pure Python code here, make sure to add type hints
        # Use Sphinx-style docstrings to document your tools, they will be used for generating tools specifications
        # Please refer to function_calling_filter_pipeline.py for an example
        pass

    def __init__(self):
        super().__init__()
        self.id = "my_tools_pipeline"
        self.name = "My Tools Pipeline"
        self.valves = self.Valves(
            **{
                **self.valves.model_dump(),
                "pipelines": ["*"],  # Connect to all pipelines
            },
        )
        self.tools = self.Tools(self)
