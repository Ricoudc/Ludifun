import 'package:flutter_tts/flutter_tts.dart';

/// Lecture à voix haute (dictée, consignes, sons, anglais) : la voix du téléphone, lente et nette.
abstract class Speaker {
  /// Lit le texte dans la langue `language` (« fr-FR », « en-GB ») ; `false` si le téléphone ne
  /// sait pas le faire (pas de voix dans cette langue).
  Future<bool> speak(String text, {String language = 'fr-FR'});

  Future<void> stop();
}

class PhoneSpeaker implements Speaker {
  final _tts = FlutterTts();
  final _ready = <String, bool>{}; // langue → voix disponible
  String? _current;

  /// Langues proches acceptées quand la première manque (anglais américain si pas britannique).
  static const _fallbacks = {
    'en-GB': ['en-GB', 'en-US'],
  };

  Future<bool> _prepare(String language) async {
    if (_current == language) return true;
    if (_ready[language] == false) return false;
    try {
      for (final candidate in _fallbacks[language] ?? [language]) {
        if (await _tts.isLanguageAvailable(candidate) == false) continue;
        await _tts.setLanguage(candidate);
        await _tts.setSpeechRate(0.4); // lent, comme une dictée en classe
        await _tts.awaitSpeakCompletion(true);
        _current = language;
        return _ready[language] = true;
      }
      return _ready[language] = false;
    } on Object {
      return _ready[language] = false;
    }
  }

  @override
  Future<bool> speak(String text, {String language = 'fr-FR'}) async {
    if (!await _prepare(language)) return false;
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
