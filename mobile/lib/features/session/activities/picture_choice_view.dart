import 'dart:async';

import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../core/speech.dart';
import '../../../models/account.dart';
import 'activity_registry.dart';
import 'common.dart';

/// « Le bon son » (SOUNDS) et « Anglais en images » (ENGLISH_WORDS), spécification §5.62 : une
/// carte à la fois — une image, un mot à compléter (« l__p »), « 🔊 » qui dit le mot dans la
/// bonne langue — et de gros boutons de réponse. Une carte d'écoute (texte « 🔊 … ») dit le mot
/// toute seule en s'affichant. Réponse : `{"answers": [[carte, choix], …]}`.
class PictureChoiceView extends StatefulWidget {
  const PictureChoiceView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<PictureChoiceView> createState() => _PictureChoiceViewState();
}

class _PictureChoiceViewState extends State<PictureChoiceView> {
  late final List<Json> _cards = [
    for (final c in widget.payload['items'] as List<dynamic>) c as Json,
  ];
  final _answers = <List<String>>[];
  Speaker? _speaker;
  bool _noVoice = false;

  bool get _done => _answers.length >= _cards.length;
  Json get _card => _done ? _cards.last : _cards[_answers.length];

  static bool _listening(Json card) => (card['text'] as String? ?? '').startsWith('🔊');

  @override
  void initState() {
    super.initState();
    _autoplay();
  }

  @override
  void dispose() {
    if (_speaker case final speaker?) unawaited(speaker.stop());
    super.dispose();
  }

  /// Une carte d'écoute dit son mot dès qu'elle s'affiche.
  void _autoplay() {
    if (_done || !_listening(_card)) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) unawaited(_say());
    });
  }

  Future<void> _say() async {
    final text = _card['say'] as String?;
    if (text == null || text.isEmpty) return;
    final speaker = _speaker ??= ListenButton.speakerFactory();
    final ok = await speaker.speak(text, language: _card['lang'] as String? ?? 'fr-FR');
    if (!mounted || ok) return;
    setState(() => _noVoice = true);
    ScaffoldMessenger.maybeOf(context)?.showSnackBar(
      const SnackBar(content: Text('Ce téléphone ne sait pas lire ce mot : demande à un adulte.')),
    );
  }

  void _choose(String choice) {
    if (_done) return;
    setState(() => _answers.add([_card['id'] as String, choice]));
    if (_done) {
      widget.onSubmit({'answers': _answers});
    } else {
      _autoplay();
    }
  }

  @override
  Widget build(BuildContext context) {
    final card = _card;
    final picture = card['picture'] as String?;
    final text = card['text'] as String? ?? '';
    final choices = (card['choices'] as List<dynamic>).cast<String>();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(widget.payload['prompt'] as String, label: ActivityInstruction.of(context)),
        const SizedBox(height: 8),
        Text(
          'Carte ${_done ? _cards.length : _answers.length + 1} sur ${_cards.length}',
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 16, color: Colors.black54),
        ),
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: Colors.black12),
          ),
          child: Column(
            children: [
              if (picture != null && picture.isNotEmpty)
                Text(picture, style: const TextStyle(fontSize: 80)),
              if (_listening(card))
                const Text('👂 Écoute bien…', style: TextStyle(fontSize: 26))
              else if (text.isNotEmpty)
                Text(
                  text,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontSize: 36,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 2,
                  ),
                ),
              if (card['say'] case final String say when say.isNotEmpty) ...[
                const SizedBox(height: 12),
                FilledButton.tonalIcon(
                  onPressed: _say,
                  icon: Icon(
                    Icons.volume_up_rounded,
                    color: _noVoice ? Colors.black26 : LudiColors.primary,
                  ),
                  label: Text(
                    _listening(card) ? 'Réécouter' : 'Écouter',
                    style: const TextStyle(fontSize: 18),
                  ),
                ),
              ],
            ],
          ),
        ),
        const SizedBox(height: 20),
        Wrap(
          alignment: WrapAlignment.center,
          spacing: 12,
          runSpacing: 12,
          children: [
            for (final (i, choice) in choices.indexed)
              _ChoiceButton(
                label: choice,
                color: i.isEven ? LudiColors.primary : LudiColors.accent,
                onPressed: _done ? null : () => _choose(choice),
              ),
          ],
        ),
      ],
    );
  }
}

/// Bouton de réponse : grand pour un son (« ou ») ou une image (🟥), plus petit pour un mot.
class _ChoiceButton extends StatelessWidget {
  const _ChoiceButton({required this.label, required this.color, required this.onPressed});

  final String label;
  final Color color;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final picture = !RegExp('[A-Za-zÀ-ÿ0-9]').hasMatch(label);
    return SizedBox(
      width: 140,
      height: 84,
      child: Material(
        color: color.withValues(alpha: 0.1),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(18),
          side: BorderSide(color: color, width: 2),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onPressed,
          child: Center(
            child: Text(
              label,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: picture ? 40 : (label.length <= 6 ? 28 : 20),
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
