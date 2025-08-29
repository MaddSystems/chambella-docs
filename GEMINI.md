# Project Overview

This project is a multi-agent chatbot system designed to provide job assistance to users through Facebook Messenger and WhatsApp. The system is built with Python and leverages the Flask web framework to handle webhook integrations with Meta's services. It uses a SQLite database to store user session data and employs the `google-generativeai` and `litellm` libraries to interact with large language models.

The core of the application is a `job_assistant_agent` that coordinates a team of sub-agents to handle different aspects of the job-seeking process, such as discovering jobs, providing information, and following up with users. The system is designed to be modular, with each agent having a specific role and responsibility.

## Building and Running

To build and run the project, you will need to have Python and the required dependencies installed.

1.  **Install Dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

2.  **Configure Environment Variables:**

    Create a `.env` file in the root of the project and add the following environment variables:

    ```
    LITELLM_PROXY_API_KEY=your_litellm_proxy_api_key
    LITELLM_PROXY_API_BASE=your_litellm_proxy_api_base
    LITELLM_MODEL=your_litellm_model
    AGENT_MODEL=your_agent_model
    VERIFY_TOKEN=your_meta_verify_token
    MESSENGER_PAGE_ACCESS_TOKEN=your_messenger_page_access_token
    WHATSAPP_ACCESS_TOKEN=your_whatsapp_access_token
    WHATSAPP_PHONE_NUMBER_ID=your_whatsapp_phone_number_id
    ```

3.  **Run the Application:**

    ```bash
    python main.py
    ```

    The application will start a web server on port 7009 by default. You can change the host and port by setting the `HOST` and `PORT` environment variables.

## Development Conventions

*   **Modular Design:** The project follows a modular design pattern, with different agents responsible for specific tasks. This makes it easier to maintain and extend the system.
*   **Asynchronous Operations:** The application uses `asyncio` and `aiohttp` to handle asynchronous operations, such as sending messages to the Meta APIs. This improves performance and scalability.
*   **Session Management:** User sessions are managed using a SQLite database and the `google.adk.sessions.DatabaseSessionService`. This allows the chatbot to maintain context and provide a personalized experience for each user.
*   **Logging:** The application uses the `logging` module to log important events and messages. The verbosity level can be controlled using the `--verbose` command-line argument.
*   **Web Interface:** The project includes a simple web interface for viewing and managing user sessions. This can be accessed by navigating to the root URL of the application in a web browser.
