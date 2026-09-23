import 'dart:async';

import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../models/account.dart';
import 'activity_registry.dart';
import 'common.dart';

/// Défi rapide : `{time_limit_s, statements:[{id,text}]}` → `{answers:[{id,value}], elapsed_ms}`.
/// Une affirmation à la fois ; le temps écoulé envoie les réponses déjà données.
class SpeedChallengeView extends StatefulWidget {
  const SpeedChallengeView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<SpeedChallengeView> createState() => _SpeedChallengeViewState();
}

class _SpeedChallengeViewState extends State<SpeedChallengeView> {
  static const _tick = Duration(milliseconds: 100);

  late final List<Choice> _statements = choicesOf(widget.payload['statements']);
  late final Duration _limit = Duration(seconds: widget.payload['time_limit_s'] as int? ?? 30);
  final _answers = <Map<String, Object>>[];
  Duration _elapsed = Duration.zero;
  Timer? _timer;
  bool _sent = false;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(_tick, (_) {
      setState(() => _elapsed += _tick);
      if (_elapsed >= _limit) _finish();
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _answer(bool value) {
    if (_sent) return;
    _answers.add({'id': _statements[_answers.length].id, 'value': value});
    if (_answers.length == _statements.length) {
      _finish();
    } else {
      setState(() {});
    }
  }

  void _finish() {
    if (_sent) return;
    _timer?.cancel();
    setState(() => _sent = true);
    widget.onSubmit({'answers': _answers, 'elapsed_ms': _elapsed.inMilliseconds});
  }

  @override
  Widget build(BuildContext context) {
    final left = (_limit - _elapsed).inSeconds.clamp(0, _limit.inSeconds);
    final index = _answers.length.clamp(0, _statements.length - 1);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Expanded(child: Text('⚡ Défi rapide', style: Theme.of(context).textTheme.titleLarge)),
            Text(
              '⏱️ $left s',
              style: TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w800,
                color: left <= 5 ? LudiColors.notMastered : null,
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        LinearProgressIndicator(
          value: 1 - _elapsed.inMilliseconds / _limit.inMilliseconds,
          minHeight: 10,
          borderRadius: BorderRadius.circular(5),
          color: left <= 5 ? LudiColors.notMastered : LudiColors.accent,
        ),
        const SizedBox(height: 24),
        Text(
          'Affirmation ${index + 1} / ${_statements.length}',
          style: Theme.of(context).textTheme.labelLarge,
        ),
        const SizedBox(height: 8),
        Prompt(_statements[index].text),
        const SizedBox(height: 32),
        Row(
          children: [
            Expanded(
              child: AnswerButton(
                label: '✅ Vrai',
                color: LudiColors.mastered,
                onPressed: _sent ? null : () => _answer(true),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: AnswerButton(
                label: '❌ Faux',
                color: LudiColors.notMastered,
                onPressed: _sent ? null : () => _answer(false),
              ),
            ),
          ],
        ),
      ],
    );
  }
}
