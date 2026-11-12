import 'dart:async';

import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../core/listening.dart';
import '../../../core/speech.dart';

/// Comment jouer, dit au niveau de la classe de l'enfant (envoyé par le serveur, étape 25).
/// Absent (serveur plus ancien) : chaque jeu garde sa consigne habituelle.
class ActivityInstruction extends InheritedWidget {
  const ActivityInstruction({required this.text, required super.child, super.key});

  final String? text;

  static String? of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<ActivityInstruction>()?.text;

  @override
  bool updateShouldNotify(ActivityInstruction oldWidget) => oldWidget.text != text;
}

/// Consigne ou question, en grand, avec « 🔊 » pour l'entendre (enfant qui lit encore mal).
class Prompt extends StatelessWidget {
  const Prompt(
    this.text, {
    this.label,
    this.passage,
    this.source,
    this.alsoRead = const [],
    this.listen = true,
    super.key,
  });

  final String text;
  final String? label;

  /// Lu après la question : les choix d'un QCM (« A : … »).
  final List<String> alsoRead;

  /// `false` pour la dictée, qui a sa propre voix (le mot ne doit pas être lu deux fois).
  final bool listen;

  /// Passage de la leçon à relire avant la question : l'enfant n'a plus la fiche.
  final String? passage;

  /// Site de confiance d'où vient la question (étape 29) : jamais confondue avec la leçon.
  final String? source;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      if (label != null) ...[
        Align(
          alignment: Alignment.centerLeft,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 7),
            decoration: BoxDecoration(
              color: const Color(0xFFEAF2FF),
              borderRadius: BorderRadius.circular(999),
            ),
            child: Semantics(
              header: true,
              child: Text(
                label!,
                style: Theme.of(context).textTheme.labelLarge
                    ?.copyWith(color: LudiColors.primary, fontWeight: FontWeight.w800),
              ),
            ),
          ),
        ),
        const SizedBox(height: 8),
      ],
      if (passage != null && passage!.isNotEmpty) ...[
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: LudiColors.primary.withValues(alpha: 0.06),
            borderRadius: BorderRadius.circular(12),
            border: Border(left: BorderSide(color: LudiColors.primary, width: 4)),
          ),
          child: Text(
            '📖 $passage',
            style: const TextStyle(fontSize: 18, height: 1.4, fontStyle: FontStyle.italic),
          ),
        ),
        const SizedBox(height: 12),
      ],
      Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Text(
              text,
              style: Theme.of(context).textTheme.headlineSmall
                  ?.copyWith(fontWeight: FontWeight.w700, height: 1.3),
            ),
          ),
          if (listen)
            ListenButton([
              label ?? ActivityInstruction.of(context) ?? '',
              passage ?? '',
              text,
              ...alsoRead,
            ]),
        ],
      ),
      if (source case final site? when site.isNotEmpty) ...[
        const SizedBox(height: 6),
        Text(
          '📚 En plus de ta leçon — d\'après $site',
          style: const TextStyle(fontSize: 14, color: Colors.black54),
        ),
      ],
    ],
  );
}

/// Le texte tel qu'il est lu à voix haute : sans émojis, un trou « ___ » devient une pause.
String spokenText(Iterable<String> parts) => parts
    .map(
      (part) => part
          .replaceAll(RegExp(r'_{2,}'), '…')
          .replaceAll(
            RegExp(r'[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}\u{200D}]', unicode: true),
            '',
          )
          .trim(),
    )
    .where((part) => part.isNotEmpty)
    .map((part) => RegExp(r'[.!?…:]$').hasMatch(part) ? part : '$part.')
    .join(' ');

/// « 🔊 » : lit la consigne et la question avec la voix française du téléphone.
class ListenButton extends StatefulWidget {
  const ListenButton(this.parts, {super.key});

  /// Remplacé dans les tests.
  static Speaker Function() speakerFactory = PhoneSpeaker.new;

  final List<String> parts;

  @override
  State<ListenButton> createState() => _ListenButtonState();
}

class _ListenButtonState extends State<ListenButton> {
  Speaker? _speaker;
  bool _speaking = false;
  bool _noVoice = false;

  @override
  void dispose() {
    if (_speaker case final speaker?) unawaited(speaker.stop());
    super.dispose();
  }

  Future<void> _listen() async {
    final speaker = _speaker ??= ListenButton.speakerFactory();
    if (_speaking) {
      await speaker.stop();
      if (mounted) setState(() => _speaking = false);
      return;
    }
    setState(() => _speaking = true);
    final ok = await speaker.speak(spokenText(widget.parts));
    if (!mounted) return;
    setState(() {
      _speaking = false;
      _noVoice = !ok;
    });
    if (!ok) {
      ScaffoldMessenger.maybeOf(context)?.showSnackBar(
        const SnackBar(
          content: Text('Ce téléphone n\'a pas de voix française : demande à un adulte de lire.'),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    label: _speaking ? 'Arrêter la lecture de la consigne' : 'Écouter la consigne',
    child: IconButton(
      tooltip: _speaking ? 'Arrêter' : 'Écouter',
      iconSize: 30,
      color: _noVoice ? Colors.black26 : LudiColors.primary,
      onPressed: _listen,
      icon: Icon(_speaking ? Icons.stop_circle_outlined : Icons.record_voice_over_outlined),
    ),
  );
}

/// Gros bouton de réponse, facile à toucher.
class AnswerButton extends StatelessWidget {
  const AnswerButton({
    required this.label,
    required this.onPressed,
    this.color = LudiColors.primary,
    this.leading,
    this.selected = false,
    super.key,
  });

  final String label;
  final VoidCallback? onPressed;
  final Color color;
  final String? leading;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    // Le jaune et les couleurs claires nécessitent un texte sombre pour rester lisibles.
    final selectedForeground = color.computeLuminance() > 0.179 ? Colors.black87 : Colors.white;
    return Semantics(
      button: true,
      selected: selected,
      child: Material(
        color: selected ? color : color.withValues(alpha: 0.1),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(18),
          side: BorderSide(color: color, width: 2),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onPressed,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 64),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Row(
                children: [
                  if (leading != null) ...[
                    CircleAvatar(
                      radius: 16,
                      backgroundColor: selected ? selectedForeground : color,
                      foregroundColor: selected ? color : Colors.white,
                      child: Text(leading!, style: const TextStyle(fontWeight: FontWeight.w800)),
                    ),
                    const SizedBox(width: 14),
                  ],
                  Expanded(
                    child: Text(
                      label,
                      style: TextStyle(
                        fontSize: 19,
                        fontWeight: FontWeight.w600,
                        color: selected ? selectedForeground : Colors.black87,
                      ),
                    ),
                  ),
                  if (selected) ...[
                    const SizedBox(width: 8),
                    Icon(Icons.check_circle, color: selectedForeground, size: 24),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// « 🎤 Dire ma réponse » (§5.78) : ce que l'enfant dit remplit la case, qu'il peut corriger
/// avant de valider. Rien n'apparaît si le téléphone ne sait pas écouter le français hors ligne.
class SpeakAnswerButton extends StatefulWidget {
  const SpeakAnswerButton({
    required this.controller,
    required this.onChanged,
    this.enabled = true,
    super.key,
  });

  /// Remplacé dans les tests.
  static VoiceInput Function() voiceFactory = PhoneVoiceInput.new;

  final TextEditingController controller;

  /// Appelé quand la voix a rempli la case (le bouton « Valider » se met à jour).
  final VoidCallback onChanged;
  final bool enabled;

  @override
  State<SpeakAnswerButton> createState() => _SpeakAnswerButtonState();
}

class _SpeakAnswerButtonState extends State<SpeakAnswerButton> {
  late final VoiceInput _voice = SpeakAnswerButton.voiceFactory();
  bool _available = false;
  bool _listening = false;
  bool _nothing = false;

  @override
  void initState() {
    super.initState();
    unawaited(
      _voice.available().then((ok) {
        if (mounted) setState(() => _available = ok);
      }),
    );
  }

  @override
  void dispose() {
    if (_listening) unawaited(_voice.stop());
    super.dispose();
  }

  void _show(String words) {
    if (!mounted || words.isEmpty) return;
    widget.controller.value = TextEditingValue(
      text: words,
      selection: TextSelection.collapsed(offset: words.length),
    );
    widget.onChanged();
  }

  Future<void> _toggle() async {
    if (_listening) {
      await _voice.stop();
      return;
    }
    setState(() {
      _listening = true;
      _nothing = false;
    });
    final words = await _voice.listen(_show);
    if (!mounted) return;
    _show(words);
    setState(() {
      _listening = false;
      _nothing = words.trim().isEmpty;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!_available) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OutlinedButton.icon(
          onPressed: widget.enabled ? _toggle : null,
          icon: Text(_listening ? '⏹️' : '🎤', style: const TextStyle(fontSize: 20)),
          label: Text(_listening ? 'Je t\'écoute… (touche pour arrêter)' : 'Dire ma réponse'),
        ),
        if (_nothing)
          const Padding(
            padding: EdgeInsets.only(top: 4),
            child: Text(
              'Je n\'ai pas bien entendu : réessaie ou écris ta réponse.',
              textAlign: TextAlign.center,
            ),
          ),
      ],
    );
  }
}
