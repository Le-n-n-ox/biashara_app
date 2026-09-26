import unittest
from unittest.mock import Mock

from utils.voice import VoiceTranscriptionError, transcribe_audio


class AudioSource:
    def __init__(self, audio_file):
        self.audio_file = audio_file

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.recognizer = Mock()
        self.recognizer.record.return_value = b"audio"
        self.module = Mock()
        self.module.Recognizer.return_value = self.recognizer
        self.module.AudioFile.side_effect = AudioSource
        self.module.UnknownValueError = type("UnknownValueError", (Exception,), {})
        self.module.RequestError = type("RequestError", (Exception,), {})

    def test_transcribes_audio_in_the_requested_language(self):
        self.recognizer.recognize_google.return_value = "M-Pesa message"

        transcript = transcribe_audio(b"recording", "sw-KE", self.module)

        self.assertEqual(transcript, "M-Pesa message")
        self.recognizer.recognize_google.assert_called_once_with(b"audio", language="sw-KE")

    def test_raises_clear_error_when_speech_is_not_understood(self):
        self.recognizer.recognize_google.side_effect = self.module.UnknownValueError()

        with self.assertRaises(VoiceTranscriptionError):
            transcribe_audio(b"recording", recognizer_module=self.module)

    def test_raises_clear_error_when_recognition_service_fails(self):
        self.recognizer.recognize_google.side_effect = self.module.RequestError()

        with self.assertRaises(VoiceTranscriptionError):
            transcribe_audio(b"recording", recognizer_module=self.module)


if __name__ == "__main__":
    unittest.main()