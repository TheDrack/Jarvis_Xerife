#-*- coding:utf-8 -*-
"""
JarvisEngine - Voice recognition and text-to-speech engine for the assistant.
"""
import logging
import sys
from typing import Optional
import speech_recognition as sr
import pyttsx3


class JarvisEngine:
    """
    Voice engine for the Jarvis assistant.
    Handles speech recognition and text-to-speech functionality.
    """
    
    def __init__(self):
        """Initialize the voice engine with pyttsx3 and speech_recognition."""
        self.audio = sr.Recognizer()
        self.maquina = pyttsx3.init()
        self.logger = logging.getLogger(__name__)
        
        # Configure logging only if no handlers exist
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            )
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def falar(self, fala: str) -> None:
        """
        Speak the given text using text-to-speech.
        
        Args:
            fala: Text to be spoken
        """
        self.logger.info(f"Speaking: {fala}")
        self.maquina.say(fala)
        self.maquina.runAndWait()
    
    def Ligar_microfone(self) -> Optional[str]:
        """
        Listen to microphone and recognize speech.
        
        Returns:
            The recognized command as a string, or None if cancelled/stopped
        """
        with sr.Microphone() as s:
            self.audio.adjust_for_ambient_noise(s)
            
            while True:
                try:
                    audio_data = self.audio.listen(s)
                    comando = self.audio.recognize_google(audio_data, language='pt-BR', show_all=True)
                    
                    if comando != []:
                        comando = self.audio.recognize_google(audio_data, language='pt-BR')
                        comando = comando.lower()
                        
                        if 'cancelar' in comando:
                            self.falar('cancelada a ação')
                            self.logger.info("Action cancelled by user")
                            # Note: restart() functionality should be handled by caller
                            return None
                        
                        elif 'fechar' in comando:
                            self.falar('fechando assistente, até mais...')
                            self.logger.info("Closing assistant")
                            sys.exit()
                        
                        elif 'parar' in comando:
                            self.falar('parando comando')
                            self.logger.info("Stopping command")
                            return None
                        else:
                            self.logger.info(f"Command recognized: {comando}")
                            return comando
                            
                except sr.UnknownValueError:
                    self.logger.warning("Could not understand audio")
                except sr.RequestError as e:
                    self.logger.error(f"Could not request results from Google Speech Recognition service; {e}")
                except Exception as e:
                    self.logger.error(f"Error in Ligar_microfone: {e}")
    
    def chamarAXerife(self) -> None:
        """
        Main voice assistant loop.
        Listens for the wake word 'xerife' and processes commands.
        """
        self.falar('Não tema a xerife chegou')
        
        with sr.Microphone() as s:
            self.audio.adjust_for_ambient_noise(s)
            
            while True:
                try:
                    audio_data = self.audio.listen(s)
                    comando = self.audio.recognize_google(audio_data, language='pt-BR', show_all=True)
                    
                    if comando != []:
                        comando = self.audio.recognize_google(audio_data, language='pt-BR')
                        comando = comando.lower()
                        
                        if 'xerife' in comando:
                            comando = comando.replace('xerife ', '')
                            self.falar('Olá')
                            self.logger.info(f"Wake word detected, command: {comando}")
                            
                            # Note: pedircomando() and comandos() functionality
                            # should be handled by the caller or integrated separately
                            # This is just the voice recognition part
                            
                        elif 'fechar' in comando:
                            self.falar('fechando assistente, até a próxima...')
                            self.logger.info("Closing assistant from chamarAXerife")
                            sys.exit()
                        else:
                            # Log unrecognized commands to file
                            self.logger.info(f"Unrecognized command (not containing 'xerife'): {comando}")
                            with open('arq01.txt', 'a') as arquivo:
                                arquivo.write(comando + "\n")
                                
                except sr.UnknownValueError:
                    self.logger.warning("Could not understand audio in chamarAXerife")
                except sr.RequestError as e:
                    self.logger.error(f"Could not request results; {e}")
                except Exception as e:
                    self.logger.error(f"Error in chamarAXerife: {e}")
