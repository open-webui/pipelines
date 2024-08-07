from langchain_core.prompts import PromptTemplate

accurate_template ="""
Let's think step by step to answer the user's question :
**Step 1: Parse Context Information**
Extract and utilize relevant knowledge from the provided context within `<context></context>` XML tags.
**Step 2: Analyze User Query**
Carefully read and comprehend the user's query, pinpointing the key concepts, entities, and intent behind the question. 
**Step 3: Determine Response**
If the answer to the user's query can be directly inferred from the context information, provide a concise and accurate response in the same language as the user's query.
**Step 4: Handle Uncertainty**
If the answer is not clear, ask the user for clarification to ensure an accurate response.
**Step 5: Avoid Context Attribution**
When formulating your response, do not indicate that the information was derived from the context.
**Step 6: Respond in User's Language**
Remember to provide the answer in Vietnamese
**Step 7: Provide Response**
- Avoid mentioning that the information was sourced from the context.
- Respond in accordance with the language of the user's question
- Generate a clear, concise, and informative response to the user's query, adhering to the guidelines outlined above.

User question: {question}

<context>
{context}
</context>
Helpful Answer:
"""
accurate_rag_prompt = PromptTemplate.from_template(accurate_template)