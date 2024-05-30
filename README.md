<p align="center">
  <a href="#"><img src="./header.png" alt="Pipelines Logo"></a>
</p>

# Pipelines: UI-Agnostic OpenAI API Plugin Framework

Welcome to **Pipelines**, an [Open WebUI](https://github.com/open-webui) initiative. Pipelines bring modular, customizable workflows to any UI client supporting OpenAI API specs – and much more! Easily extend functionalities, integrate unique logic, and create dynamic workflows with just a few lines of code.

## 🚀 Why Choose Pipelines?

- **Seamless Integration:** Compatible with any UI/client supporting OpenAI API specs.
- **Limitless Possibilities:** Easily add custom logic and integrate Python libraries, from AI agents to home automation APIs.
- **Custom Hooks:** Build and integrate custom pipelines.

## 🔧 How It Works

<p align="center">
  <a href="#"><img src="./docs/images/workflow.png" alt="Pipelines Workflow"></a>
</p>

Integrating Pipelines with any OpenAI API-compatible UI client is simple. Launch your Pipelines instance and set the OpenAI URL on your client to the Pipelines URL. That's it! You're ready to leverage any Python library for your needs.

## 📂 Directory Structure and Examples

The `/pipelines` directory is the core of your setup. Add new modules, customize existing ones, and manage your workflows here. All the pipelines in the `/pipelines` directory will be **automatically loaded** when the server launches.

### Integration Examples

Find various integration examples in the `/pipelines/examples` directory. These examples show how to integrate different functionalities, providing a foundation for building your own custom pipelines.

## 📦 Installation and Setup

Get started with Pipelines in a few steps:

1. **Ensure Python 3.11 is installed.**
2. **Clone the Pipelines repository:**

   ```sh
   git clone https://github.com/open-webui/pipelines.git
   cd pipelines
   ```

3. **Install the required dependencies:**

   ```sh
   pip install -r requirements.txt
   ```

4. **Start the Pipelines server:**

   ```sh
   sh ./start.sh
   ```

Once the server is running, set the OpenAI URL on your client to the Pipelines URL. This unlocks the full capabilities of Pipelines, integrating any Python library and creating custom workflows tailored to your needs.

## ⚡ Quick Start Example

1. **Copy and paste `rate_limit_filter_pipeline.py` from `/pipelines/examples` to the `/pipelines` folder.**
2. **Run the Pipelines server:** It will be hosted at `http://localhost:9099` by default.
3. **Configure Open WebUI:**

   - In Open WebUI, go to **Settings > Connections > OpenAI API**.
   - Set the API URL to `http://localhost:9099` and set the API key (default: `0p3n-w3bu!`). Your filter should now be active.

4. **Adjust Settings:**
   - In the admin panel, go to **Admin Settings > Pipelines tab**.
   - Select the filter and change the valve values directly from the WebUI.

That's it! You're now set up with Pipelines. Enjoy building customizable AI integrations effortlessly!

## 🎉 Work in Progress

We’re continuously evolving! We'd love to hear your feedback and understand which hooks and features would best suit your use case. Feel free to reach out and become a part of our Open WebUI community!

Our vision is to push **Pipelines** to become the ultimate plugin framework for our AI interface, **Open WebUI**. Imagine **Open WebUI** as the WordPress of AI interfaces, with **Pipelines** being its diverse range of plugins. Join us on this exciting journey! 🌍
