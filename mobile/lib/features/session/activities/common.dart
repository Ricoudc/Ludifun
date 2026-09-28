import 'package:flutter/material.dart';

import '../../../app/theme.dart';

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

/// Consigne ou question, en grand.
class Prompt extends StatelessWidget {
  const Prompt(this.text, {this.label, super.key});

  final String text;
  final String? label;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      if (label != null) ...[
        Text(
          label!,
          style: Theme.of(context).textTheme.labelLarge?.copyWith(color: LudiColors.primary),
        ),
        const SizedBox(height: 8),
      ],
      Text(
        text,
        style: Theme.of(context).textTheme.headlineSmall
            ?.copyWith(fontWeight: FontWeight.w700, height: 1.3),
      ),
    ],
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
  Widget build(BuildContext context) => Semantics(
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
                    backgroundColor: selected ? Colors.white : color,
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
                      color: selected ? Colors.white : Colors.black87,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    ),
  );
}
