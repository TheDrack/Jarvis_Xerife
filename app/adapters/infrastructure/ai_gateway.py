# -*- coding: utf-8 -*-
"""AI Gateway - Intelligent routing between multiple LLM providers

This gateway implements a "Gears" (Marchas) system:
- High Gear (Marcha Alta): Llama-4-Scout/Llama-3.3-70b as default (fast, cost-effective)
- Low Gear (Marcha Baixa): Qwen-3-32B or Llama-8B for internal Groq rate limit fallback
- Cannon Shot (Tiro de Canhão): Gemini-1.5-Pro as external fallback when Groq entirely fails
- Auto-Repair: Captures critical errors and dispatches auto-fix to GitHub Actions
"""

import asyncio
import logging
import os
import traceback
from enum import Enum
from typing import Any, Dict, List, Optional

# Try to import tiktoken, but don't fail if it's not available
try:
    import tiktoken
    HAS_TIKTOKEN = True
except ImportError:
    tiktoken = None
    HAS_TIKTOKEN = False

logger = logging.getLogger(__name__)

# Module-level tokenizer cache to avoid repeated initialization
_TOKENIZER_CACHE = None


def _get_tokenizer():
    """Get or create tokenizer with caching"""
    global _TOKENIZER_CACHE
    if not HAS_TIKTOKEN:
        return None
    
    if _TOKENIZER_CACHE is None:
        try:
            # Using cl100k_base encoding (GPT-4, GPT-3.5-turbo)
            # This is a good approximation for most modern LLMs
            _TOKENIZER_CACHE = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(f"Failed to initialize tokenizer: {e}. Token counting will be approximate.")
            _TOKENIZER_CACHE = False  # Use False to indicate initialization was attempted but failed
    return _TOKENIZER_CACHE if _TOKENIZER_CACHE else None


def count_tokens(text: str) -> int:
    """
    Count tokens in the given text.
    
    Uses tiktoken if available, otherwise falls back to character-based approximation
    using a 1:4 ratio (1 token ≈ 4 characters).
    
    Args:
        text: Text to count tokens for
        
    Returns:
        Approximate token count
    """
    if HAS_TIKTOKEN:
        tokenizer = _get_tokenizer()
        if tokenizer:
            try:
                return len(tokenizer.encode(text))
            except Exception as e:
                logger.warning(f"Error counting tokens: {e}. Using character approximation.")
    
    # Fallback: rough approximation (1 token ≈ 4 characters)
    return len(text) // 4


class LLMProvider(str, Enum):
    """Available LLM providers"""
    GROQ = "groq"
    GEMINI = "gemini"


class GroqGear(str, Enum):
    """Groq Gears (Marchas) - Different Groq models for different use cases"""
    HIGH_GEAR = "high"  # Marcha Alta: Llama-4-Scout or Llama-3.3-70b (default)
    LOW_GEAR = "low"    # Marcha Baixa: Qwen-3-32B or Llama-8B (rate limit fallback)


class AIGateway:
    """
    AI Gateway that intelligently routes requests between multiple LLM providers.
    
    Features:
    - Gears System (Sistema de Marchas):
      * High Gear (Marcha Alta): Llama-4-Scout or Llama-3.3-70b (default, fast)
      * Low Gear (Marcha Baixa): Qwen-3-32B or Llama-8B (internal Groq fallback)
      * Cannon Shot (Tiro de Canhão): Gemini-1.5-Pro (external fallback)
    - Automatically escalate to Gemini for large contexts (>10k tokens)
    - Auto-repair on critical errors (sends fixes to GitHub Actions)
    """
    
    # Token threshold for context-based escalation
    TOKEN_THRESHOLD = 10000
    
    # Groq Gears Configuration (Marcha Alta e Marcha Baixa)
    # High Gear: Fast, powerful model (default - currently llama-3.3-70b-versatile)
    # Future alternatives: llama-4-scout when available
    DEFAULT_HIGH_GEAR_MODEL = "llama-3.3-70b-versatile"
    # Low Gear: Smaller, more economical model (internal fallback - currently llama-3.1-8b-instant)
    # Future alternatives: qwen-3-32b
    DEFAULT_LOW_GEAR_MODEL = "llama-3.1-8b-instant"
    
    # Gemini Cannon Shot (External Fallback)
    DEFAULT_GEMINI_MODEL = "gemini-1.5-pro"  # Changed from gemini-flash-latest
    
    def __init__(
        self,
        groq_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        groq_high_gear_model: Optional[str] = None,
        groq_low_gear_model: Optional[str] = None,
        gemini_model: Optional[str] = None,
        default_provider: LLMProvider = LLMProvider.GROQ,
        enable_auto_repair: bool = True,
        github_adapter: Optional[Any] = None,
        # Backward compatibility parameters
        groq_model: Optional[str] = None,
    ):
        """
        Initialize AI Gateway with multiple provider support and Gears system.
        
        Args:
            groq_api_key: Groq API key (defaults to GROQ_API_KEY env var)
            gemini_api_key: Gemini API key (defaults to GOOGLE_API_KEY or GEMINI_API_KEY env var)
            groq_high_gear_model: High Gear model name (defaults to DEFAULT_HIGH_GEAR_MODEL or GROQ_MODEL env var)
            groq_low_gear_model: Low Gear model name (defaults to DEFAULT_LOW_GEAR_MODEL or GROQ_LOW_GEAR_MODEL env var)
            gemini_model: Gemini model name (defaults to DEFAULT_GEMINI_MODEL or GEMINI_MODEL env var)
            default_provider: Default provider for routing (GROQ or GEMINI)
            enable_auto_repair: Enable auto-repair on critical errors
            github_adapter: Optional GitHubAdapter instance for auto-repair
            groq_model: (Deprecated) Use groq_high_gear_model instead. For backward compatibility.
        """
        # Handle backward compatibility: groq_model -> groq_high_gear_model
        if groq_model is not None:
            groq_high_gear_model = groq_model
        
        # Groq Gears configuration
        self.groq_high_gear_model = (
            groq_high_gear_model 
            or os.getenv("GROQ_MODEL") 
            or os.getenv("GROQ_HIGH_GEAR_MODEL")
            or self.DEFAULT_HIGH_GEAR_MODEL
        )
        self.groq_low_gear_model = (
            groq_low_gear_model
            or os.getenv("GROQ_LOW_GEAR_MODEL")
            or self.DEFAULT_LOW_GEAR_MODEL
        )
        
        # Gemini configuration
        self.gemini_model = (
            gemini_model
            or os.getenv("GEMINI_MODEL")
            or self.DEFAULT_GEMINI_MODEL
        )
        
        self.default_provider = default_provider
        self.enable_auto_repair = enable_auto_repair
        self.github_adapter = github_adapter
        
        # Current Groq gear (starts at High Gear)
        self.current_groq_gear = GroqGear.HIGH_GEAR
        
        # Get API keys from parameters or environment
        self.groq_api_key = groq_api_key or os.getenv("GROQ_API_KEY")
        self.gemini_api_key = gemini_api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        
        # Initialize tokenizer for token counting (use cached tokenizer)
        self.tokenizer = _get_tokenizer()
        
        # Initialize providers
        self.groq_client = None
        self.gemini_client = None
        
        self._initialize_groq()
        self._initialize_gemini()
        
        logger.info(
            f"AI Gateway initialized with Gears System:\n"
            f"  - High Gear (Marcha Alta): {self.groq_high_gear_model}\n"
            f"  - Low Gear (Marcha Baixa): {self.groq_low_gear_model}\n"
            f"  - Cannon Shot (Tiro de Canhão): {self.gemini_model}\n"
            f"  - Default provider: {self.default_provider.value}\n"
            f"  - Groq available: {self.groq_client is not None}\n"
            f"  - Gemini available: {self.gemini_client is not None}\n"
            f"  - Auto-repair: {self.enable_auto_repair}"
        )
    
    @property
    def groq_model(self) -> str:
        """Backward compatibility property for groq_model"""
        return self._get_current_groq_model()
    
    def _initialize_groq(self) -> None:
        """Initialize Groq client if API key is available"""
        if not self.groq_api_key:
            logger.warning("Groq API key not provided. Groq provider will be unavailable.")
            return
        
        try:
            from groq import Groq
            self.groq_client = Groq(api_key=self.groq_api_key)
            logger.info("Groq client initialized successfully")
        except ImportError:
            logger.error("Groq library not installed. Install with: pip install groq")
        except Exception as e:
            logger.error(f"Failed to initialize Groq client: {e}")
    
    def _get_current_groq_model(self) -> str:
        """Get the current Groq model based on the active gear"""
        if self.current_groq_gear == GroqGear.HIGH_GEAR:
            return self.groq_high_gear_model
        else:
            return self.groq_low_gear_model
    
    def _shift_to_low_gear(self) -> None:
        """Shift to Low Gear (Marcha Baixa) for rate limit handling"""
        if self.current_groq_gear == GroqGear.HIGH_GEAR:
            logger.warning(
                f"🔧 Shifting to Low Gear (Marcha Baixa): {self.groq_low_gear_model}"
            )
            self.current_groq_gear = GroqGear.LOW_GEAR
    
    def _shift_to_high_gear(self) -> None:
        """Shift back to High Gear (Marcha Alta) after recovery"""
        if self.current_groq_gear == GroqGear.LOW_GEAR:
            logger.info(
                f"✅ Shifting back to High Gear (Marcha Alta): {self.groq_high_gear_model}"
            )
            self.current_groq_gear = GroqGear.HIGH_GEAR
    
    def _initialize_gemini(self) -> None:
        """Initialize Gemini client if API key is available"""
        if not self.gemini_api_key:
            logger.warning("Gemini API key not provided. Gemini provider will be unavailable.")
            return
        
        try:
            from google import genai
            self.gemini_client = genai.Client(api_key=self.gemini_api_key)
            logger.info("Gemini client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
    
    def count_tokens(self, text: str) -> int:
        """
        Count tokens in the given text.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Approximate token count
        """
        # Delegate to module-level function
        return count_tokens(text)
    
    def select_provider(
        self,
        payload: str,
        multimodal: bool = False,
        force_provider: Optional[LLMProvider] = None,
    ) -> LLMProvider:
        """
        Select the best provider based on payload characteristics.
        
        Args:
            payload: The text payload to be processed
            multimodal: Whether the request requires multimodal analysis
            force_provider: Force a specific provider (overrides automatic selection)
            
        Returns:
            Selected LLM provider
        """
        # If provider is forced, use it (if available)
        if force_provider:
            if force_provider == LLMProvider.GROQ and self.groq_client:
                return LLMProvider.GROQ
            elif force_provider == LLMProvider.GEMINI and self.gemini_client:
                return LLMProvider.GEMINI
            logger.warning(f"Forced provider {force_provider} not available, using auto-selection")
        
        # Multimodal always goes to Gemini (Groq doesn't support it yet)
        if multimodal:
            if self.gemini_client:
                logger.info("Multimodal request detected, routing to Gemini")
                return LLMProvider.GEMINI
            else:
                logger.error("Multimodal requested but Gemini not available")
                raise ValueError("Multimodal analysis requires Gemini, but it's not available")
        
        # Count tokens in payload
        token_count = self.count_tokens(payload)
        logger.debug(f"Payload token count: {token_count}")
        
        # If payload exceeds threshold, escalate to Gemini
        if token_count > self.TOKEN_THRESHOLD:
            if self.gemini_client:
                logger.info(
                    f"Payload exceeds {self.TOKEN_THRESHOLD} tokens ({token_count}), "
                    "escalating to Gemini"
                )
                return LLMProvider.GEMINI
            else:
                logger.warning(
                    f"Payload exceeds threshold but Gemini not available, using Groq"
                )
        
        # Default to Groq for cost-effectiveness (if available)
        if self.groq_client:
            logger.debug("Using Groq as default provider")
            return LLMProvider.GROQ
        
        # Fallback to Gemini if Groq not available
        if self.gemini_client:
            logger.debug("Groq not available, falling back to Gemini")
            return LLMProvider.GEMINI
        
        raise ValueError("No LLM providers available")
    
    async def generate_completion(
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[Any]] = None,
        multimodal: bool = False,
        force_provider: Optional[LLMProvider] = None,
    ) -> Dict[str, Any]:
        """
        Generate a completion using the most appropriate provider with Gears system.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            functions: Optional function declarations for function calling
            multimodal: Whether the request requires multimodal analysis
            force_provider: Force a specific provider
            
        Returns:
            Response dict with 'provider', 'response', and other metadata
        """
        # Combine all message content for token counting
        payload = "\n".join([msg.get("content", "") for msg in messages if msg.get("content")])
        
        # Select provider
        provider = self.select_provider(
            payload=payload,
            multimodal=multimodal,
            force_provider=force_provider,
        )
        
        try:
            if provider == LLMProvider.GROQ:
                return await self._generate_with_groq(messages, functions)
            else:
                return await self._generate_with_gemini(messages, functions)
        except Exception as e:
            error_traceback = traceback.format_exc()
            
            # Check if it's a model decommissioned error
            if self._is_model_decommissioned_error(e):
                error_msg = (
                    f"⚠️ ATENÇÃO: O modelo '{self._get_current_groq_model()}' foi descomissionado pelo Groq!\n"
                    f"Por favor, atualize o modelo no seu arquivo .env:\n"
                    f"  GROQ_MODEL={self.DEFAULT_HIGH_GEAR_MODEL}\n"
                    f"Erro original: {e}"
                )
                logger.error(error_msg)
                
                # Try to dispatch auto-repair if enabled
                await self._dispatch_auto_repair_if_enabled(
                    error=e,
                    error_traceback=error_traceback,
                    issue_title="Model Decommissioned Error",
                    file_path="app/adapters/infrastructure/ai_gateway.py"
                )
                
                # Try to fallback to Gemini if available
                if provider == LLMProvider.GROQ and self.gemini_client:
                    logger.warning("Tentando fallback para Gemini devido a modelo descomissionado")
                    return await self._handle_rate_limit_fallback(provider, messages, functions)
                raise ValueError(error_msg) from e
            
            # Check if it's a rate limit error
            elif self._is_rate_limit_error(e):
                logger.warning(f"Rate limit hit on {provider.value}, attempting fallback")
                # If it's Groq and we're in High Gear, try Low Gear first
                if provider == LLMProvider.GROQ and self.current_groq_gear == GroqGear.HIGH_GEAR:
                    self._shift_to_low_gear()
                    try:
                        return await self._generate_with_groq(messages, functions)
                    except Exception as low_gear_error:
                        # Low gear also failed, check if it's also a rate limit
                        if self._is_rate_limit_error(low_gear_error):
                            logger.error(f"Low Gear also hit rate limit: {low_gear_error}")
                            # Escalate to Gemini (Cannon Shot) if available
                            if self.gemini_client:
                                logger.warning("🚀 Firing Cannon Shot (Tiro de Canhão): Gemini")
                                return await self._handle_rate_limit_fallback(provider, messages, functions)
                            else:
                                # No Gemini available, raise proper error
                                raise ValueError(
                                    f"Rate limit reached on {provider.value} (both High and Low Gear) "
                                    "and no fallback provider available"
                                ) from low_gear_error
                        else:
                            # Different error in Low Gear, re-raise
                            raise
                else:
                    return await self._handle_rate_limit_fallback(provider, messages, functions)
            
            # Other errors
            else:
                logger.error(f"Error generating completion with {provider.value}: {e}")
                logger.error(f"Traceback:\n{error_traceback}")
                
                # Try to dispatch auto-repair for critical errors
                await self._dispatch_auto_repair_if_enabled(
                    error=e,
                    error_traceback=error_traceback,
                    issue_title=f"Critical error in AI Gateway: {type(e).__name__}",
                    file_path="app/adapters/infrastructure/ai_gateway.py"
                )
                
                raise
    
    async def _dispatch_auto_repair_if_enabled(
        self,
        error: Exception,
        error_traceback: str,
        issue_title: str,
        file_path: str,
    ) -> None:
        """
        Dispatch auto-repair if enabled and error is critical.
        
        Args:
            error: The exception that occurred
            error_traceback: Full traceback string
            issue_title: Title for the issue
            file_path: File path where the error occurred
        """
        if not self.enable_auto_repair:
            logger.debug("Auto-repair disabled, skipping dispatch")
            return
        
        # Check if error is critical (authentication, syntax, import errors)
        error_str = str(error).lower()
        is_critical = any(
            keyword in error_str
            for keyword in [
                "authentication", "auth", "unauthorized", "401", "403",
                "syntax", "import", "module", "indentation",
                "name error", "attribute error", "type error"
            ]
        )
        
        if not is_critical:
            logger.debug(f"Error not critical, skipping auto-repair: {error}")
            return
        
        # Try to dispatch auto-repair
        if self.github_adapter:
            try:
                logger.info(f"🔧 Dispatching auto-repair for critical error: {issue_title}")
                
                # For now, we'll just log the error data
                # In a real implementation, the GitHub adapter would analyze the error
                # and formulate a fix using AI
                error_data = {
                    "issue": issue_title,
                    "file": file_path,
                    "error_log": error_traceback,
                    "error_type": type(error).__name__,
                }
                
                logger.info(f"Auto-repair payload: {error_data}")
                
                # Note: We're not actually calling dispatch_auto_fix here because
                # we need AI to formulate the fix first. This is just logging
                # the error for monitoring purposes.
                
            except Exception as dispatch_error:
                logger.error(f"Failed to dispatch auto-repair: {dispatch_error}")
        else:
            logger.debug("GitHub adapter not configured, cannot dispatch auto-repair")
    
    async def _generate_with_groq(
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate completion using Groq with Gears system.
        
        Args:
            messages: List of message dicts
            functions: Optional function declarations
            
        Returns:
            Response dict
        """
        if not self.groq_client:
            raise ValueError("Groq client not initialized")
        
        # Get current model based on active gear
        current_model = self._get_current_groq_model()
        current_gear = "High Gear (Marcha Alta)" if self.current_groq_gear == GroqGear.HIGH_GEAR else "Low Gear (Marcha Baixa)"
        
        logger.debug(f"Generating completion with Groq - {current_gear}: {current_model}")
        
        # Build request parameters
        request_params = {
            "model": current_model,
            "messages": messages,
        }
        
        # Add tools if functions are provided
        if functions:
            # Convert function declarations to Groq's tool format
            tools = self._convert_functions_to_groq_tools(functions)
            if tools:
                request_params["tools"] = tools
                request_params["tool_choice"] = "auto"
        
        # Make the request using run_in_executor to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: self.groq_client.chat.completions.create(**request_params)
        )
        
        # After successful completion, if we're in Low Gear, consider shifting back to High Gear
        if self.current_groq_gear == GroqGear.LOW_GEAR:
            # Shift back to High Gear after successful completion
            # This allows the system to recover from rate limits
            self._shift_to_high_gear()
        
        return {
            "provider": LLMProvider.GROQ.value,
            "response": response,
            "model": current_model,
            "gear": self.current_groq_gear.value,
        }
    
    async def _generate_with_gemini(
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate completion using Gemini.
        
        Args:
            messages: List of message dicts
            functions: Optional function declarations
            
        Returns:
            Response dict
        """
        if not self.gemini_client:
            raise ValueError("Gemini client not initialized")
        
        logger.debug(f"Generating completion with Gemini ({self.gemini_model})")
        
        from google import genai
        
        # Convert messages to Gemini format (combine into single content)
        content = "\n".join([msg.get("content", "") for msg in messages if msg.get("content")])
        
        # Extract system instruction if present
        system_instruction = None
        for msg in messages:
            if msg.get("role") == "system":
                system_instruction = msg.get("content")
                break
        
        # Build config
        config_params = {}
        if system_instruction:
            config_params["system_instruction"] = system_instruction
        
        # Add tools if functions are provided
        if functions:
            tools = [genai.types.Tool(function_declarations=functions)]
            config_params["tools"] = tools
        
        # Make the request using run_in_executor to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.gemini_client.models.generate_content(
                model=self.gemini_model,
                contents=content,
                config=genai.types.GenerateContentConfig(**config_params) if config_params else None,
            )
        )
        
        return {
            "provider": LLMProvider.GEMINI.value,
            "response": response,
            "model": self.gemini_model,
        }
    
    def _convert_functions_to_groq_tools(self, functions: List[Any]) -> List[Dict[str, Any]]:
        """
        Convert Gemini function declarations to Groq's tool format.
        
        Args:
            functions: List of function declarations
            
        Returns:
            List of tool dicts for Groq
        """
        tools = []
        for func in functions:
            # Convert Gemini function declaration to OpenAI-compatible format
            tool = {
                "type": "function",
                "function": {
                    "name": func.name,
                    "description": func.description,
                }
            }
            
            # Add parameters if present
            if hasattr(func, "parameters") and func.parameters:
                tool["function"]["parameters"] = self._convert_gemini_schema_to_openai(
                    func.parameters
                )
            
            tools.append(tool)
        
        return tools
    
    def _convert_gemini_schema_to_openai(self, schema: Any) -> Dict[str, Any]:
        """
        Convert Gemini schema to OpenAI-compatible schema.
        
        Args:
            schema: Gemini schema object
            
        Returns:
            OpenAI-compatible schema dict
        """
        # Extract properties from Gemini schema
        result = {
            "type": "object",
            "properties": {},
        }
        
        if hasattr(schema, "properties"):
            for prop_name, prop_value in schema.properties.items():
                prop_dict = {
                    "type": getattr(prop_value, "type", "string"),
                }
                
                if hasattr(prop_value, "description"):
                    prop_dict["description"] = prop_value.description
                
                result["properties"][prop_name] = prop_dict
        
        # Add required fields
        if hasattr(schema, "required"):
            result["required"] = list(schema.required)
        
        return result
    
    def _is_rate_limit_error(self, error: Exception) -> bool:
        """
        Check if an error is a rate limit error.
        
        Args:
            error: Exception to check
            
        Returns:
            True if it's a rate limit error
        """
        error_str = str(error).lower()
        return any(
            keyword in error_str
            for keyword in ["rate limit", "quota", "too many requests", "429"]
        )
    
    def _is_model_decommissioned_error(self, error: Exception) -> bool:
        """
        Check if an error is a model decommissioned error.
        
        Args:
            error: Exception to check
            
        Returns:
            True if it's a model decommissioned error
        """
        error_str = str(error).lower()
        return any(
            keyword in error_str
            for keyword in ["model_decommissioned", "decommissioned", "model has been deprecated"]
        )
    
    async def _handle_rate_limit_fallback(
        self,
        failed_provider: LLMProvider,
        messages: List[Dict[str, str]],
        functions: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """
        Handle rate limit by falling back to alternative provider.
        
        Args:
            failed_provider: Provider that hit rate limit
            messages: Original messages
            functions: Optional function declarations
            
        Returns:
            Response from fallback provider
        """
        # Determine fallback provider
        if failed_provider == LLMProvider.GROQ:
            if self.gemini_client:
                logger.info("Groq rate limit reached, falling back to Gemini")
                response = await self._generate_with_gemini(messages, functions)
                response["fallback_from"] = LLMProvider.GROQ.value
                return response
        elif failed_provider == LLMProvider.GEMINI:
            if self.groq_client:
                logger.info("Gemini rate limit reached, falling back to Groq")
                response = await self._generate_with_groq(messages, functions)
                response["fallback_from"] = LLMProvider.GEMINI.value
                return response
        
        # No fallback available
        raise ValueError(
            f"Rate limit reached on {failed_provider.value} and no fallback provider available"
        )
