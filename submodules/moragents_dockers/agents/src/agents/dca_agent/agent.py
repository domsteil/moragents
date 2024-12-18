import json
import asyncio
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from decimal import Decimal
from cdp import Cdp, Wallet

from src.agents.dca_agent import tools

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class DCAAgent:
    def __init__(self, config, llm, embeddings): 
        """ 
        Initialize the DCAAgent for managing DCA strategies.
        """
        self.config = config
        self.llm = llm
        self.embeddings = embeddings
        self.client: Cdp = Cdp()
        self.tools_provided = tools.get_tools()
        self._sync_task: Optional[asyncio.Task] = None
        self._executors: Dict[str, Any] = {}

        # Mapping of function names to handler methods
        self.function_handlers = {
            "handle_dollar_cost_average": self.handle_dollar_cost_average,
            "handle_pause_dca_strategy": self.handle_pause_dca_strategy,
            "handle_resume_dca_strategy": self.handle_resume_dca_strategy,
            "handle_cancel_dca_strategy": self.handle_cancel_dca_strategy
        }

    def chat(self, request):
        """Handle incoming chat requests"""
        try:
            data = request.get_json()
            if not data:
                return {"error": "Invalid request data"}, 400

            # Handle chat prompt
            if 'prompt' in data:
                prompt = data['prompt']
                response, role, next_turn_agent = self.handle_request(prompt)
                return {"role": role, "content": response, "next_turn_agent": next_turn_agent}

            return {"error": "Missing required parameters"}, 400

        except Exception as e:
            logger.error(f"Error in chat method: {str(e)}")
            return {"error": str(e)}, 500

    def handle_request(self, message: str) -> Tuple[str, str, Optional[str]]:
        """Process request and route to appropriate handler"""
        logger.info(f"Processing message: {message}")

        # System prompt that includes descriptions of available functions
        prompt = [
            {
                "role": "system",
                "content": (
                    "You are a DCA (Dollar Cost Averaging) agent that helps users create and manage "
                    "cryptocurrency trading strategies. Available actions:\n"
                    "1. Create new DCA strategies with specific intervals and amounts\n"
                    "2. Pause active strategies\n"
                    "3. Resume paused strategies\n"
                    "4. Cancel existing strategies\n"
                )
            }
        ]

        if isinstance(message, dict):
            user_content = message.get('content', '')
        else:
            user_content = message

        prompt.append({
            "role": "user",
            "content": user_content
        })

        result = self.llm.create_chat_completion(
            messages=prompt,
            tools=self.tools_provided,
            tool_choice="auto",
            temperature=0.01
        )

        try:
            choice = result["choices"][0]["message"]
            if "tool_calls" in choice:
                func = choice["tool_calls"][0]['function']
                func_name = func["name"].strip().split()[-1]
                logger.info(f"Function name: {func_name}")
                args = json.loads(func["arguments"])
                return self.handle_function_call(func_name, args)
            return choice.get('content', ''), "assistant", None
        except Exception as e:
            logger.error(f"Request processing error: {e}")
            return f"Error processing request: {str(e)}", "assistant", None

    def handle_function_call(self, func_name: str, args: Dict[str, Any], chain_id: Optional[str] = None, wallet_address: Optional[str] = None) -> Tuple[str, str, Optional[str]]:
        handler = self.function_handlers.get(func_name)
        if handler:
            return handler(args, chain_id, wallet_address)
        else:
            logger.error(f"Function '{func_name}' not supported.")
            return f"Error: Function '{func_name}' not supported.", "assistant", None

    def handle_dollar_cost_average(self, args: Dict[str, Any], chain_id: Optional[str], wallet_address: Optional[str]) -> Tuple[str, str, Optional[str]]:
        """Handle dollar cost averaging strategy creation"""
        try:
            res, role = tools.handle_create_dca_strategy(
                token_address=args["token_address"],
                amount=args["amount"],
                interval_type=args["interval_type"],
                total_periods=args.get("total_periods"),
                min_price=args.get("min_price"),
                max_price=args.get("max_price"),
                max_slippage=args.get("max_slippage", 0.01),
                gasless=args.get("gasless", False)
            )
            logger.info(f"DCA Strategy creation result: {res}")
            return f"Successfully created DCA strategy with ID: {res['strategy_id']}", role, None
        except tools.ValidationError as e:
            logger.error(f"Validation error in DCA creation: {str(e)}")
            return str(e), "assistant", None
        except tools.ExecutionError as e:
            logger.error(f"Execution error in DCA creation: {str(e)}")
            return str(e), "assistant", None

    def handle_pause_dca_strategy(self, args: Dict[str, Any], chain_id: Optional[str], wallet_address: Optional[str]) -> Tuple[str, str, Optional[str]]:
        """Handle pausing a DCA strategy"""
        try:
            res, role = tools.handle_pause_dca_strategy(args["strategy_id"])
            logger.info(f"Strategy pause result: {res}")
            return f"Successfully paused strategy {args['strategy_id']}", role, None
        except tools.StrategyNotFoundError as e:
            logger.error(f"Strategy not found: {str(e)}")
            return str(e), "assistant", None
        except tools.ExecutionError as e:
            logger.error(f"Error pausing strategy: {str(e)}")
            return str(e), "assistant", None

    def handle_resume_dca_strategy(self, args: Dict[str, Any], chain_id: Optional[str], wallet_address: Optional[str]) -> Tuple[str, str, Optional[str]]:
        """Handle resuming a DCA strategy"""
        try:
            res, role = tools.handle_resume_dca_strategy(args["strategy_id"])
            logger.info(f"Strategy resume result: {res}")
            return f"Successfully resumed strategy {args['strategy_id']}", role, None
        except tools.StrategyNotFoundError as e:
            logger.error(f"Strategy not found: {str(e)}")
            return str(e), "assistant", None
        except tools.ExecutionError as e:
            logger.error(f"Error resuming strategy: {str(e)}")
            return str(e), "assistant", None

    def handle_cancel_dca_strategy(self, args: Dict[str, Any], chain_id: Optional[str], wallet_address: Optional[str]) -> Tuple[str, str, Optional[str]]:
        """Handle cancelling a DCA strategy"""
        try:
            res, role = tools.handle_cancel_dca_strategy(args["strategy_id"])
            logger.info(f"Strategy cancellation result: {res}")
            return f"Successfully cancelled strategy {args['strategy_id']}", role, None
        except tools.StrategyNotFoundError as e:
            logger.error(f"Strategy not found: {str(e)}")
            return str(e), "assistant", None
        except tools.ExecutionError as e:
            logger.error(f"Error cancelling strategy: {str(e)}")
            return str(e), "assistant", None
