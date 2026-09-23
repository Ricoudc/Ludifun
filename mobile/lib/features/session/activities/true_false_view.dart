import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../models/account.dart';
import 'activity_registry.dart';
import 'common.dart';

/// Vrai ou faux : `{statement}` → `{value}`.
class TrueFalseView extends StatefulWidget {
  const TrueFalseView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<TrueFalseView> createState() => _TrueFalseViewState();
}

class _TrueFalseViewState extends State<TrueFalseView> {
  bool? _value;

  void _answer(bool value) {
    if (_value != null) return;
    setState(() => _value = value);
    widget.onSubmit({'value': value});
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Prompt(widget.payload['statement'] as String, label: 'Vrai ou faux ?'),
      const SizedBox(height: 32),
      Row(
        children: [
          Expanded(
            child: AnswerButton(
              label: '✅ Vrai',
              color: LudiColors.mastered,
              selected: _value == true,
              onPressed: () => _answer(true),
            ),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: AnswerButton(
              label: '❌ Faux',
              color: LudiColors.notMastered,
              selected: _value == false,
              onPressed: () => _answer(false),
            ),
          ),
        ],
      ),
    ],
  );
}
