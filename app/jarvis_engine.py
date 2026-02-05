# -*- coding: utf-8 -*-
"""
JarvisEngine - Main engine for voice-activated assistant
"""
import speech_recognition as sr
import pyttsx3


class JarvisEngine:
    """
    Main engine that handles voice recognition and activation keyword detection
    """
    
    def __init__(self, activation_keyword='xerife'):
        """
        Initialize the Jarvis engine
        
        Args:
            activation_keyword: The keyword to activate the assistant (default: 'xerife')
        """
        self.activation_keyword = activation_keyword.lower()
        self.audio_recognizer = sr.Recognizer()
        self.tts_engine = pyttsx3.init()
        self.running = False
        
    def speak(self, text):
        """
        Speak the given text using text-to-speech
        
        Args:
            text: Text to speak
        """
        self.tts_engine.say(text)
        self.tts_engine.runAndWait()
        
    def listen(self):
        """
        Listen for voice input and return recognized text
        
        Returns:
            str: Recognized text or empty string if recognition failed
        """
        with sr.Microphone() as source:
            self.audio_recognizer.adjust_for_ambient_noise(source)
            try:
                audio = self.audio_recognizer.listen(source, timeout=5, phrase_time_limit=10)
                text = self.audio_recognizer.recognize_google(audio, language='pt-BR')
                return text.lower()
            except sr.UnknownValueError:
                return ""
            except sr.RequestError as e:
                print(f"Erro ao conectar ao serviço de reconhecimento: {e}")
                return ""
            except sr.WaitTimeoutError:
                return ""
                
    def wait_for_activation(self):
        """
        Wait for the activation keyword to be spoken
        
        Returns:
            str: The full command including activation keyword, or empty string
        """
        command = self.listen()
        if command and self.activation_keyword in command:
            return command
        return ""
        
    def extract_command(self, full_text):
        """
        Extract the actual command from the full text, removing activation keyword
        
        Args:
            full_text: The full recognized text
            
        Returns:
            str: Command text without activation keyword
        """
        if not full_text:
            return ""
        return full_text.replace(self.activation_keyword, '').strip()
        
    def start(self, command_processor):
        """
        Start the main listening loop
        
        Args:
            command_processor: CommandProcessor instance to handle commands
        """
        self.running = True
        self.speak('Assistente iniciado. Aguardando comando de ativação.')
        
        while self.running:
            # Wait for activation keyword
            full_command = self.wait_for_activation()
            
            if full_command:
                # Extract the actual command
                command = self.extract_command(full_command)
                
                if not command:
                    self.speak('Olá, estou ouvindo')
                    # Listen for the next command
                    command = self.listen()
                    
                if command:
                    # Check for exit command
                    if 'fechar' in command or 'sair' in command:
                        self.speak('Encerrando assistente. Até logo!')
                        self.running = False
                        break
                        
                    # Process the command
                    if not command_processor.process(command):
                        self.speak('Comando não reconhecido')
                        
    def stop(self):
        """Stop the engine"""
        self.running = False
