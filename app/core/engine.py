# -*- coding: utf-8 -*-
"""Jarvis Voice Engine - Main voice recognition and synthesis engine"""

import sys
from typing import Callable, Optional

import pyttsx3
import speech_recognition as sr

from app.core.config import settings


class JarvisEngine:
    """Main voice recognition and synthesis engine for Jarvis Assistant"""

    def __init__(self) -> None:
        """Initialize the Jarvis voice engine"""
        self.recognizer: sr.Recognizer = sr.Recognizer()
        self.tts_engine: pyttsx3.Engine = pyttsx3.init()
        self.is_running: bool = False

    def speak(self, text: str) -> None:
        """
        Convert text to speech

        Args:
            text: Text to be spoken
        """
        self.tts_engine.say(text)
        self.tts_engine.runAndWait()

    def listen(self, timeout: Optional[float] = None) -> Optional[str]:
        """
        Listen for voice input and convert to text

        Args:
            timeout: Maximum time to wait for speech (seconds)

        Returns:
            Recognized text in lowercase, or None if recognition failed
        """
        with sr.Microphone() as source:
            if settings.ambient_noise_adjustment:
                self.recognizer.adjust_for_ambient_noise(source)

            try:
                audio = self.recognizer.listen(source, timeout=timeout)
                # Try to recognize with show_all first to check if anything was detected
                result = self.recognizer.recognize_google(
                    audio, language=settings.language, show_all=True
                )

                if result:
                    # Get the best match
                    command = self.recognizer.recognize_google(audio, language=settings.language)
                    return command.lower()
                return None

            except sr.WaitTimeoutError:
                return None
            except sr.UnknownValueError:
                return None
            except sr.RequestError as e:
                print(f"Could not request results from Google Speech Recognition service; {e}")
                return None

    def wait_for_wake_word(self, on_command: Callable[[str], None]) -> None:
        """
        Main loop waiting for wake word and processing commands

        Args:
            on_command: Callback function to process commands
        """
        self.is_running = True
        self.speak(f"Não tema, {settings.wake_word} chegou")

        with sr.Microphone() as source:
            if settings.ambient_noise_adjustment:
                self.recognizer.adjust_for_ambient_noise(source)

            while self.is_running:
                try:
                    audio = self.recognizer.listen(source)
                    result = self.recognizer.recognize_google(
                        audio, language=settings.language, show_all=True
                    )

                    if result:
                        command = self.recognizer.recognize_google(
                            audio, language=settings.language
                        ).lower()

                        if settings.wake_word in command:
                            # Remove wake word from command
                            command = command.replace(f"{settings.wake_word} ", "")
                            self.speak("Olá")

                            if command:
                                on_command(command)
                            else:
                                # Request new command
                                self.speak("Diga um comando")
                                new_command = self.listen()
                                if new_command:
                                    new_command = new_command.replace(f"{settings.wake_word} ", "")
                                    on_command(new_command)

                        elif "fechar" in command:
                            self.speak("Fechando assistente, até a próxima...")
                            self.stop()

                except sr.UnknownValueError:
                    continue
                except sr.RequestError as e:
                    print(f"Error: {e}")
                    continue
                except KeyboardInterrupt:
                    self.stop()

    def stop(self) -> None:
        """Stop the voice engine"""
        self.is_running = False
        sys.exit(0)

    def get_command(self) -> Optional[str]:
        """
        Get a single voice command

        Returns:
            Recognized command or None
        """
        command = self.listen()

        if command:
            if "cancelar" in command:
                self.speak("Ação cancelada")
                return None
            elif "fechar" in command:
                self.speak("Fechando assistente, até mais...")
                self.stop()
            elif "parar" in command:
                self.speak("Parando comando")
                return None

        return command
