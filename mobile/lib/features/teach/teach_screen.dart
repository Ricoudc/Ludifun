import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/teach.dart';
import '../session/activities/common.dart' show ListenButton;

/// « Enseigne-moi » (§83) : l'enfant devient professeur et explique une notion à Ludi, qui pose
/// une ou deux questions de relance, puis fait le bilan.
class TeachScreen extends ConsumerStatefulWidget {
  const TeachScreen({required this.teachId, super.key});

  final String teachId;

  @override
  ConsumerState<TeachScreen> createState() => _TeachScreenState();
}

class _TeachScreenState extends ConsumerState<TeachScreen> {
  final _answer = TextEditingController();
  Teach? _teach;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _answer.addListener(() => setState(() {}));
    _fetch();
  }

  @override
  void dispose() {
    _answer.dispose();
    super.dispose();
  }

  Future<void> _fetch() async {
    try {
      final teach = await ref.read(apiProvider).teaching(widget.teachId);
      if (mounted) setState(() => _teach = teach);
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
  }

  Future<void> _send() async {
    final text = _answer.text.trim();
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final teach = await ref.read(apiProvider).teachAnswer(widget.teachId, text);
      _answer.clear();
      if (mounted) setState(() => _teach = teach);
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
    if (mounted) setState(() => _busy = false);
  }

  void _back() {
    final lesson = _teach?.lessonId;
    context.go(lesson == null ? Routes.childHome : Routes.lesson(lesson));
  }

  @override
  Widget build(BuildContext context) {
    final teach = _teach;
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: _back),
        title: const Text('Enseigne-moi'),
      ),
      body: CenteredBody(
        top: true,
        children: [
          if (teach == null && _error == null)
            const Center(child: CircularProgressIndicator())
          else if (teach != null) ...[
            Text(
              '🧑‍🏫 Tu es le professeur ! Explique « ${teach.label} » à Ludi.',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 12),
            for (final message in teach.messages) _Bubble(message),
            if (_busy)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: Text('🧑‍🎓 Ludi réfléchit…', style: TextStyle(fontSize: 16)),
              ),
            const SizedBox(height: 12),
            if (teach.finished) ..._end(context, teach) else ..._input(),
          ],
          if (_error != null) ErrorMessage(_error!),
        ],
      ),
    );
  }

  List<Widget> _input() => [
    TextField(
      controller: _answer,
      enabled: !_busy,
      minLines: 3,
      maxLines: 6,
      maxLength: 1000,
      decoration: const InputDecoration(
        labelText: 'Mon explication',
        helperText: 'Tu peux aussi dicter avec le micro 🎤 du clavier.',
        border: OutlineInputBorder(),
      ),
    ),
    const SizedBox(height: 8),
    FilledButton(
      onPressed: _busy || _answer.text.trim().isEmpty ? null : _send,
      child: const Text('Expliquer à Ludi'),
    ),
  ];

  List<Widget> _end(BuildContext context, Teach teach) => [
    Card(
      color: LudiColors.mastered.withValues(alpha: 0.08),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (teach.summary case final summary?)
              Text(summary, style: const TextStyle(fontSize: 18, height: 1.35)),
            if (teach.validated == true) ...[
              const SizedBox(height: 8),
              const Text(
                '⭐ Niveau « Expliquer » validé !',
                style: TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.w800,
                  color: LudiColors.mastered,
                ),
              ),
            ],
          ],
        ),
      ),
    ),
    const SizedBox(height: 16),
    FilledButton(onPressed: _back, child: const Text('Retour à la leçon')),
  ];
}

class _Bubble extends StatelessWidget {
  const _Bubble(this.message);

  final TeachMessage message;

  @override
  Widget build(BuildContext context) {
    final ludi = message.fromLudi;
    final bubble = Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 10),
      constraints: const BoxConstraints(maxWidth: 480),
      decoration: BoxDecoration(
        color: ludi
            ? LudiColors.primary.withValues(alpha: 0.08)
            : LudiColors.accent.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Text(
        ludi ? '🧑‍🎓 ${message.text}' : message.text,
        style: const TextStyle(fontSize: 17, height: 1.35),
      ),
    );
    return Row(
      mainAxisAlignment: ludi ? MainAxisAlignment.start : MainAxisAlignment.end,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Flexible(child: bubble),
        if (ludi) ListenButton([message.text]),
      ],
    );
  }
}
