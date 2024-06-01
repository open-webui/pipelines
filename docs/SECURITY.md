# Security Policy

Our primary goal is to ensure the protection and confidentiality of sensitive data stored by users on Pipelines. Additionally, we aim to maintain a secure and trusted environment for executing Pipelines, which effectively function as a plugin system with arbitrary code execution capabilities.

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |
| others  | :x:                |

## Secure Pipelines Execution

To mitigate risks associated with the Pipelines plugin system, we recommend the following best practices:

1. **Trusted Sources**: Only fetch and execute Pipelines from trusted sources. Do not retrieve or run Pipelines from untrusted or unknown origins.

2. **Fixed Versions**: Instead of pulling the latest version of a Pipeline, consider using a fixed, audited version to ensure stability and security.

3. **Sandboxing**: Pipelines are executed in a sandboxed environment to limit their access to system resources and prevent potential harm.

4. **Code Review**: All Pipelines undergo a thorough code review process before being approved for execution on our platform.

5. **Monitoring**: We continuously monitor the execution of Pipelines for any suspicious or malicious activities.

## Reporting a Vulnerability

If you discover a security issue within our system, please notify us immediately via a pull request or contact us on discord. We take all security reports seriously and will respond promptly.

## Product Security

We regularly audit our internal processes and system's architecture for vulnerabilities using a combination of automated and manual testing techniques. We are committed to implementing Static Application Security Testing (SAST) and Software Composition Analysis (SCA) scans in our project to further enhance our security posture.