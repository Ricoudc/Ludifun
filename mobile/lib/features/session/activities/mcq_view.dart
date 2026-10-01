import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../models/account.dart';
import 'activity_registry.dart';
import 'common.dart';

/// QCM : `{prompt, choices:[{id,text}]}` → `{choice_id}`.
class McqView extends StatefulWidget {
  const McqView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<McqView> createState() => _McqViewState();
}

class _McqViewState extends State<McqView> {
  static const _letters = ['A', 'B', 'C', 'D', 'E', 'F'];
  static const _colors = [
    LudiColors.primary,
    LudiColors.accent,
    LudiColors.mastered,
    Color(0xFF1E88E5),
    Color(0xFFD81B60),
    Color(0xFF6D4C41),
  ];
  String? _chosen;

  void _choose(String id) {
    if (_chosen != null) return;
    setState(() => _chosen = id);
    widget.onSubmit({'choice_id': id});
  }

  @override
  Widget build(BuildContext context) {
    final choices = choicesOf(widget.payload['choices']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(
          widget.payload['prompt'] as String,
          label: ActivityInstruction.of(context),
          passage: widget.payload['passage'] as String?,
        ),
        const SizedBox(height: 24),
        for (final (i, choice) in choices.indexed) ...[
          AnswerButton(
            label: choice.text,
            leading: _letters[i % _letters.length],
            color: _colors[i % _colors.length],
            selected: _chosen == choice.id,
            onPressed: () => _choose(choice.id),
          ),
          const SizedBox(height: 12),
        ],
      ],
    );
  }
}
