<p align="center">
  <a href="#"><img src="./header.png" alt="Pipelines Logo"></a>
</p>

# Pipelines: UI-Agnostic OpenAI API Plugin Framework

Welcome to **Pipelines**, [Open WebUI](https://github.com/open-webui) initiative that brings modular, customizable workflows to any UI client supporting OpenAI API specs – and much more! Dive into a world where you can effortlessly extend functionalities, integrate unique logic, and create dynamic agentic workflows, all with a few lines of code.

## 🚀 Why Pipelines?

- **Seamless Integration:** Compatible with any UI/client that supports OpenAI API specs.
- **Endless Possibilities:** Got a specific need? Pipelines make it easy to add your custom logic and functionalities. Integrate any Python library, from AI agents via libraries like CrewAI to API calls for home automation – the sky's the limit!
- **Custom Hooks:** Build and integrate custom RAG pipelines and more.

## 🔧 How It Works

<p align="center">
  <a href="#"><img src="./docs/images/workflow.png" alt="Pipelines Workflow"></a>
</p>

Integrating Pipelines with any OpenAI API-compatible UI client is a breeze. Simply launch your Pipelines instance and set the OpenAI URL on your client to the Pipelines URL. That's it! You're now ready to leverage any Python library, whether you want an agent to manage your home or need a custom pipeline for your enterprise workflow.

## 📂 Directory Structure and Examples

Everything you need to build and extend Pipelines can be found in the `/pipelines` directory. This directory is the heart of your Pipelines setup, where you can add new modules, customize existing ones, and manage your workflow integrations.

### Integration Examples

To help you get started quickly, we've included a variety of integration examples in the `/pipeline/examples` directory. These examples demonstrate how to integrate different functionalities and libraries, providing a solid foundation for building your own custom pipelines.

## 📦 Installation and Setup

To get started with Pipelines, follow these simple steps:

1. **Ensure you have Python 3.11 installed.**
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

Once the server is running, you can set the OpenAI URL on your client to the Pipelines URL. This allows you to leverage the full capabilities of Pipelines, integrating any Python library and creating custom workflows tailored to your needs.

Happy coding and welcome to the future of customizable AI integrations with **Pipelines**!

## 🎉 Work in Progress

We’re continuously evolving! We'd love to hear your feedback and understand which hooks and features would best suit your use case. Feel free to reach out and become a part of our Open WebUI community!

Our vision is to push **Pipelines** to become the ultimate plugin framework for our AI interface, **Open WebUI**. Imagine **Open WebUI** as the WordPress of AI interfaces, with **Pipelines** being its diverse range of plugins. Join us on this exciting journey! 🌍
