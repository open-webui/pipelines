# Example of langgraph integration
## Python version: 3.11
## Feature
1. Using langgraph stream writer and custom mode of stream to integrate langgraph with open webui pipeline.
2. Support \<think\> block display.
## Prerequirement
Install the open webui pipeline.
You can follow the docs : https://docs.openwebui.com/pipelines/#-quick-start-with-docker

## Usage
### 1. Upload pipeline file
Upload `langgraph_stream_pipeline.py` to the open webui pipeline. 

### 2. Enable the uploaded pipeline
Properly set up your langgraph api url.

And choose **"LangGraph stream"** as your model.

### 2. Install dependencies
Under the folder `pipelines/examples/pipelines/integrations/langgraph_pipeline`, run command below :
```
pip install -r requirements.txt
``` 
### 3. Start langgraph api server
Run command below :
```
uvicorn langgraph_example:app --reload
```