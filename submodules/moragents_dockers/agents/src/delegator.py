import importlib
import logging
import json

from langchain.schema import SystemMessage, HumanMessage, AIMessage

logger = logging.getLogger(__name__)

# Configurable default agent
DEFAULT_AGENT = "general purpose and context-based rag agent"


class Delegator:
    def __init__(self, config, llm, embeddings):
        self.config = config
        self.llm = llm  # This is now a ChatOllama instance
        self.embeddings = embeddings
        self.agents = self.load_agents(config)
        logger.info("Delegator initialized with %d agents", len(self.agents))

    def load_agents(self, config):
        agents = {}
        for agent_info in config["agents"]:
            try:
                module = importlib.import_module(agent_info["path"])
                agent_class = getattr(module, agent_info["class"])
                agent_instance = agent_class(
                    agent_info,
                    self.llm,
                    self.embeddings,
                )
                agents[agent_info["name"]] = agent_instance
                logger.info("Loaded agent: %s", agent_info["name"])
            except Exception as e:
                logger.error("Failed to load agent %s: %s", agent_info["name"], str(e))
        return agents

    def get_delegator_response(self, prompt, upload_state):
        available_agents = [
            agent_info["name"]
            for agent_info in self.config["agents"]
            if not (agent_info["upload_required"] and not upload_state)
        ]
        logger.info(f"Available agents: {available_agents}")

        agent_descriptions = "\n".join(
            f"- {agent_info['name']}: {agent_info['description']}"
            for agent_info in self.config["agents"]
            if agent_info["name"] in available_agents
        )

        system_prompt = (
            "Your name is Morpheus. "
            "Your primary function is to select the correct agent based on the user's input. "
            "You MUST use the 'select_agent' function to select an agent. "
            f"Available agents and their descriptions: {agent_descriptions}\n"
            "Analyze the user's input and select the most appropriate agent. "
        )

        tools = [
            {
                "name": "select_agent",
                "description": "Choose which agent should be used to respond to the user query",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent": {
                            "type": "string",
                            "enum": available_agents,
                            "description": "The name of the agent to be used to respond to the user query",
                        },
                    },
                    "required": ["agent"],
                },
            }
        ]

        agent_selection_llm = self.llm.bind_tools(tools)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt),
        ]

        result = agent_selection_llm.invoke(messages)
        tool_calls = result.tool_calls
        if not tool_calls:
            raise ValueError("No agent was selected by the model.")

        selected_agent = tool_calls[0]
        logger.info(f"Selected agent: {selected_agent}")
        selected_agent_name = selected_agent.get("args").get("agent")

        return {"agent": selected_agent_name}

    def delegate_chat(self, agent_name, request):
        logger.info(f"Attempting to delegate chat to agent: {agent_name}")
        agent = self.agents.get(agent_name)
        if agent:
            logger.info(f"Successfully found agent: {agent_name}")
            try:
                result = agent.chat(request)
                logger.info(f"Chat delegation to {agent_name} completed successfully")
                logger.info(f"Response from {agent_name}: {result}")
                return agent_name, result
            except Exception as e:
                logger.error(f"Error during chat delegation to {agent_name}: {str(e)}")
                return {"error": f"Chat delegation to {agent_name} failed"}, 500
        else:
            logger.warning(f"Attempted to delegate to non-existent agent: {agent_name}")
            return {"error": f"No such agent registered: {agent_name}"}, 400

    def delegate_route(self, agent_name, request, method_name):
        agent = self.agents.get(agent_name)
        if agent:
            if hasattr(agent, method_name):
                logger.info("Delegating %s to agent: %s", method_name, agent_name)
                method = getattr(agent, method_name)
                return method(request)
            else:
                logger.warning(
                    "Method %s not found in agent %s", method_name, agent_name
                )
                return {
                    "error": f"No such method '{method_name}' in agent '{agent_name}'"
                }, 400
        logger.warning("Attempted to delegate to non-existent agent: %s", agent_name)
        return {"error": "No such agent registered"}, 400
