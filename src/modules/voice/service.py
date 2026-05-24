"""
Voice Service - služba pro hlasové ovládání (placeholder pro budoucí implementaci)
"""
from __future__ import annotations

from typing import Optional, Callable
from dataclasses import dataclass

# Pokusit se importovat hlasové knihovny
try:
    import speech_recognition as sr
    SPEECH_RECOGNITION_AVAILABLE = True
except ImportError:
    SPEECH_RECOGNITION_AVAILABLE = False

try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False


@dataclass
class VoiceCommand:
    """Reprezentace hlasového příkazu"""
    text: str
    confidence: float
    language: str = "cs-CZ"


class VoiceService:
    """
    Služba pro hlasové ovládání.
    
    POZNÁMKA: Toto je placeholder implementace.
    Pro plnou funkcionalitu je potřeba nainstalovat:
    - SpeechRecognition: pip install SpeechRecognition
    - pyttsx3: pip install pyttsx3
    - PyAudio: pip install PyAudio (pro mikrofon)
    """
    
    def __init__(self):
        self.recognizer = None
        self.engine = None
        self.commands: dict[str, Callable] = {}
        
        if SPEECH_RECOGNITION_AVAILABLE:
            self.recognizer = sr.Recognizer()
        
        if PYTTSX3_AVAILABLE:
            try:
                self.engine = pyttsx3.init()
                # Nastavit český hlas (pokud je dostupný)
                voices = self.engine.getProperty('voices')
                for voice in voices:
                    if 'czech' in voice.name.lower() or 'cs' in voice.id.lower():
                        self.engine.setProperty('voice', voice.id)
                        break
            except Exception as e:
                print(f"[VOICE] Chyba při inicializaci TTS: {e}")
                self.engine = None
    
    def is_speech_recognition_available(self) -> bool:
        """Zkontroluje dostupnost rozpoznávání řeči"""
        return SPEECH_RECOGNITION_AVAILABLE and self.recognizer is not None
    
    def is_tts_available(self) -> bool:
        """Zkontroluje dostupnost text-to-speech"""
        return PYTTSX3_AVAILABLE and self.engine is not None
    
    def get_status(self) -> dict:
        """Vrátí status hlasových služeb"""
        return {
            "speech_recognition": self.is_speech_recognition_available(),
            "text_to_speech": self.is_tts_available(),
            "speech_recognition_installed": SPEECH_RECOGNITION_AVAILABLE,
            "tts_installed": PYTTSX3_AVAILABLE
        }
    
    def listen(self, timeout: int = 5) -> Optional[VoiceCommand]:
        """
        Poslouchá hlasový vstup z mikrofonu.
        
        Args:
            timeout: Časový limit v sekundách
            
        Returns:
            VoiceCommand objekt nebo None
        """
        if not self.is_speech_recognition_available():
            print("[VOICE] Rozpoznávání řeči není k dispozici")
            return None
        
        try:
            with sr.Microphone() as source:
                print("[VOICE] Poslouchám...")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.recognizer.listen(source, timeout=timeout)
            
            # Rozpoznat řeč pomocí Google Speech Recognition
            text = self.recognizer.recognize_google(audio, language="cs-CZ")
            print(f"[VOICE] Rozpoznáno: {text}")
            
            return VoiceCommand(
                text=text,
                confidence=1.0,  # Google API nevrací confidence
                language="cs-CZ"
            )
        except sr.WaitTimeoutError:
            print("[VOICE] Timeout - žádný vstup")
            return None
        except sr.UnknownValueError:
            print("[VOICE] Nepodařilo se rozpoznat řeč")
            return None
        except sr.RequestError as e:
            print(f"[VOICE] Chyba služby rozpoznávání: {e}")
            return None
        except Exception as e:
            print(f"[VOICE] Chyba: {e}")
            return None
    
    def speak(self, text: str) -> bool:
        """
        Přečte text nahlas.
        
        Args:
            text: Text k přečtení
            
        Returns:
            True pokud bylo úspěšné
        """
        if not self.is_tts_available():
            print(f"[VOICE] TTS není k dispozici. Text: {text}")
            return False
        
        try:
            self.engine.say(text)
            self.engine.runAndWait()
            return True
        except Exception as e:
            print(f"[VOICE] Chyba při čtení textu: {e}")
            return False
    
    def register_command(self, phrase: str, callback: Callable) -> None:
        """
        Zaregistruje hlasový příkaz.
        
        Args:
            phrase: Fráze pro aktivaci příkazu
            callback: Funkce, která se zavolá při rozpoznání
        """
        self.commands[phrase.lower()] = callback
    
    def process_command(self, command: VoiceCommand) -> bool:
        """
        Zpracuje hlasový příkaz.
        
        Args:
            command: VoiceCommand objekt
            
        Returns:
            True pokud byl příkaz rozpoznán a proveden
        """
        text = command.text.lower()
        
        for phrase, callback in self.commands.items():
            if phrase in text:
                try:
                    callback()
                    return True
                except Exception as e:
                    print(f"[VOICE] Chyba při provádění příkazu: {e}")
                    return False
        
        return False
    
    def set_speech_rate(self, rate: int) -> None:
        """
        Nastaví rychlost řeči.
        
        Args:
            rate: Rychlost (typicky 150-200)
        """
        if self.engine:
            self.engine.setProperty('rate', rate)
    
    def set_volume(self, volume: float) -> None:
        """
        Nastaví hlasitost.
        
        Args:
            volume: Hlasitost (0.0 - 1.0)
        """
        if self.engine:
            self.engine.setProperty('volume', max(0.0, min(1.0, volume)))






