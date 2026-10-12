import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../models/account.dart';
import 'activity_registry.dart';
import 'common.dart';

/// Carte mémoire : `{front, back}` → `{self_assessment: knew | didnt_know}`.
class FlashcardView extends StatefulWidget {
  const FlashcardView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<FlashcardView> createState() => _FlashcardViewState();
}

class _FlashcardViewState extends State<FlashcardView> {
  bool _flipped = false;
  bool _sent = false;

  void _assess(String value) {
    if (_sent) return;
    setState(() => _sent = true);
    widget.onSubmit({'self_assessment': value});
  }

  @override
  Widget build(BuildContext context) {
    final face = _flipped ? widget.payload['back'] as String : widget.payload['front'] as String;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                _flipped
                    ? 'Le savais-tu ?'
                    : ActivityInstruction.of(context) ?? 'Te souviens-tu de ce que ça veut dire ?',
                style: Theme.of(context).textTheme.labelLarge?.copyWith(color: LudiColors.primary),
              ),
            ),
            // La face visible seulement : jamais le verso avant de retourner la carte.
            ListenButton([
              if (!_flipped)
                ActivityInstruction.of(context) ?? 'Te souviens-tu de ce que ça veut dire ?',
              face,
            ], key: ValueKey(_flipped)),
          ],
        ),
        const SizedBox(height: 12),
        GestureDetector(
          onTap: () => setState(() => _flipped = true),
          child: AnimatedSwitcher(
            duration: const Duration(milliseconds: 300),
            transitionBuilder: (child, animation) =>
                ScaleTransition(scale: animation, child: child),
            child: Card(
              key: ValueKey(_flipped),
              color: _flipped ? LudiColors.accent.withValues(alpha: 0.15) : Colors.white,
              child: Container(
                constraints: const BoxConstraints(minHeight: 200),
                alignment: Alignment.center,
                padding: const EdgeInsets.all(24),
                child: Text(
                  face,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall
                      ?.copyWith(fontWeight: FontWeight.w700),
                ),
              ),
            ),
          ),
        ),
        const SizedBox(height: 24),
        if (!_flipped)
          FilledButton.icon(
            onPressed: () => setState(() => _flipped = true),
            icon: const Icon(Icons.flip),
            label: const Text('Retourner la carte'),
          )
        else
          Row(
            children: [
              Expanded(
                child: AnswerButton(
                  label: 'Je ne savais pas',
                  color: LudiColors.toReview,
                  onPressed: () => _assess('didnt_know'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: AnswerButton(
                  label: 'Je savais 👍',
                  color: LudiColors.mastered,
                  onPressed: () => _assess('knew'),
                ),
              ),
            ],
          ),
      ],
    );
  }
}
