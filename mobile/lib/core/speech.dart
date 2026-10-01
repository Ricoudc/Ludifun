import 'package:flutter_tts/flutter_tts.dart';

/// Lecture à voix haute (dictée) : la voix française du téléphone, lente et nette.
abstract class Speaker {
  /// Lit le texte ; `false` si le téléphone ne sait pas le faire (pas de voix française).
  Future<bool> speak(String text);

  Future<void> stop();
}

class PhoneSpeaker implements Speaker {
  final _tts = FlutterTts();
  bool? _ready;

  Future<bool> _prepare() async {
    if (_ready != null) return _ready!;
    try {
      final available = await _tts.isLanguageAvailable('fr-FR');
      if (available == false) return _ready = false;
      await _tts.setLanguage('fr-FR');
      await _tts.setSpeechRate(0.4); // lent, comme une dictée en classe
      await _tts.awaitSpeakCompletion(true);
      return _ready = true;
    } on Object {
      return _ready = false;
    }
  }

  @override
  Future<bool> speak(String text) async {
    if (!await _prepare()) return false;
    try {
      await _tts.speak(text);
      return true;
    } on Object {
      return false;
    }
  }

  @override
  Future<void> stop() async {
    try {
      await _tts.stop();
    } on Object {
      // rien à arrêter
    }
  }
}
