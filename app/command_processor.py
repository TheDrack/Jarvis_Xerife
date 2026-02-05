# -*- coding: utf-8 -*-
"""
CommandProcessor - Processes voice commands and routes them to appropriate actions
"""


class CommandProcessor:
    """
    Processes commands received from voice input
    """
    
    def __init__(self):
        """Initialize command processor"""
        self.commands = {}
        
    def register_command(self, keyword, action):
        """
        Register a command keyword with its action
        
        Args:
            keyword: The command keyword to listen for
            action: The function to execute when keyword is detected
        """
        self.commands[keyword] = action
        
    def process(self, command_text):
        """
        Process a command text and execute the appropriate action
        
        Args:
            command_text: The command string to process
            
        Returns:
            bool: True if command was processed, False otherwise
        """
        if not command_text:
            return False
            
        command_text = command_text.lower().strip()
        
        # Check each registered command
        for keyword, action in self.commands.items():
            if keyword in command_text:
                # Remove the keyword and pass remaining text to action
                remaining = command_text.replace(keyword, '').strip()
                try:
                    action(remaining)
                    return True
                except Exception as e:
                    print(f"Erro ao executar comando '{keyword}': {e}")
                    return False
                    
        return False
