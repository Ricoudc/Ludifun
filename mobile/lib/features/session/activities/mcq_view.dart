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
          alsoRead: [
            for (final (i, choice) in choices.indexed)
              '${_letters[i % _letters.length]} : ${choice.text}',
          ],
        ),
        const SizedBox(height: 22),
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: LudiColors.primary.withValues(alpha: 0.12)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Padding(
                padding: EdgeInsets.only(left: 4, bottom: 14),
                child: Row(
                  children: [
                    Icon(Icons.touch_app_rounded, color: LudiColors.primary, size: 22),
                    SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Choisis ta réponse',
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800),
                      ),
                    ),
                  ],
                ),
              ),
              for (final (i, choice) in choices.indexed) ...[
                AnswerButton(
                  label: choice.text,
                  leading: _letters[i % _letters.length],
                  color: _colors[i % _colors.length],
                  selected: _chosen == choice.id,
                  onPressed: () => _choose(choice.id),
                ),
                if (i != choices.length - 1) const SizedBox(height: 10),
              ],
            ],
          ),
        ),
      ],
    );
  }
}
