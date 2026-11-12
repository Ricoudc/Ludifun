import 'package:speech_to_text/speech_to_text.dart';

/// Réponse dite à voix haute (§5.78) : la reconnaissance vocale du téléphone, **sur le
/// téléphone seulement** (`onDevice`). La voix d'un enfant n'est jamais envoyée sur Internet :
/// si le téléphone ne sait pas reconnaître le français hors ligne, le micro n'est pas proposé.
abstract class VoiceInput {
  /// `true` si le téléphone peut écouter en français, sans Internet.
  Future<bool> available();

  /// Écoute jusqu'à un silence ; `onWords` reçoit le texte reconnu (au fur et à mesure, puis le
  /// dernier). Rend le texte final, vide si rien n'a été compris.
  Future<String> listen(void Function(String words) onWords);

  Future<void> stop();
}

class PhoneVoiceInput implements VoiceInput {
  final _speech = SpeechToText();
  bool? _ready;

  @override
  Future<bool> available() async {
    if (_ready case final ready?) return ready;
    try {
      final ok = await _speech.initialize();
      if (!ok) return _ready = false;
      final locales = await _speech.locales();
      return _ready = locales.any((l) => l.localeId.toLowerCase().startsWith('fr'));
    } on Object {
      return _ready = false;
    }
  }

  @override
  Future<String> listen(void Function(String words) onWords) async {
    if (!await available()) return '';
    var last = '';
    var done = false;
    try {
      await _speech.listen(
        onResult: (result) {
          last = result.recognizedWords;
          onWords(last);
          if (result.finalResult) done = true;
        },
        listenOptions: SpeechListenOptions(
          localeId: 'fr_FR',
          onDevice: true, // jamais d'envoi de la voix à un service en ligne
          partialResults: true,
          cancelOnError: true,
          listenMode: ListenMode.confirmation,
          listenFor: const Duration(seconds: 20),
          pauseFor: const Duration(seconds: 3),
        ),
      );
      // Attend la fin de l'écoute (silence, durée maximale ou erreur).
      for (var i = 0; i < 250 && !done && _speech.isListening; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 100));
      }
    } on Object {
      return last;
    }
    return last;
  }

  @override
  Future<void> stop() async {
    try {
      await _speech.stop();
    } on Object {
      // rien à arrêter
    }
  }
}
