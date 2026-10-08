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
  // Ni vert ni rouge : ces couleurs disent « juste » et « faux » dans la correction, un enfant
  // ne doit pas y voir un indice avant de répondre.
  static const _colors = [
    LudiColors.primary,
    LudiColors.accent,
    Color(0xFF1E88E5),
    Color(0xFF8E24AA),
    Color(0xFF6D4C41),
    Color(0xFF546E7A),
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
          source: widget.payload['source'] as String?,
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
