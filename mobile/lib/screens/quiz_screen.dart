import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';

import '../api/models.dart';
import '../main.dart';
import '../widgets/question_views.dart';
import 'result_screen.dart';

/// Écran 4 : enchaînement des questions, correction immédiate, chrono en mode défi.
class QuizScreen extends StatefulWidget {
  final RevisionSession session;
  const QuizScreen({super.key, required this.session});

  @override
  State<QuizScreen> createState() => _QuizScreenState();
}

class _QuizScreenState extends State<QuizScreen> {
  int _index = 0;
  AnswerResult? _result;
  bool _sending = false;
  final _watch = Stopwatch()..start();
  Timer? _timer;
  int? _remaining;

  QuizQuestion get _question => widget.session.questions[_index];

  @override
  void initState() {
    super.initState();
    final limit = widget.session.timeLimitS;
    if (limit != null) {
      _remaining = limit;
      _timer = Timer.periodic(const Duration(seconds: 1), (_) {
        setState(() => _remaining = _remaining! - 1);
        if (_remaining! <= 0) _finish();
      });
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _submit(String answer) async {
    if (_sending || _result != null) return;
    setState(() => _sending = true);
    try {
      final result = await api.answer(widget.session.id, _question.id, answer, _watch.elapsedMilliseconds);
      setState(() => _result = result);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  void _next() {
    if (_index + 1 >= widget.session.questions.length) {
      _finish();
      return;
    }
    setState(() {
      _index++;
      _result = null;
      _watch.reset();
    });
  }

  bool _finishing = false;

  Future<void> _finish() async {
    if (_finishing) return;
    _finishing = true;
    _timer?.cancel();
    try {
      final report = await api.finish(widget.session.id);
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => ResultScreen(report: report)));
    } catch (e) {
      _finishing = false;
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    }
  }

  Widget _questionView() {
    final q = _question;
    final enabled = _result == null && !_sending;
    return switch (q.kind) {
      'qcm' || 'vrai_faux' => ChoiceQuestion(question: q, enabled: enabled, onAnswer: _submit),
      'flashcard' => FlashcardQuestion(key: ValueKey(q.id), question: q, enabled: enabled, onAnswer: _submit),
      'association' => MatchingQuestion(
          key: ValueKey(q.id), question: q, enabled: enabled, onAnswer: (m) => _submit(jsonEncode(m))),
      _ => TextQuestion(key: ValueKey(q.id), question: q, enabled: enabled, onAnswer: _submit,
          multiline: q.kind == 'question_ouverte'),
    };
  }

  @override
  Widget build(BuildContext context) {
    final total = widget.session.questions.length;
    final result = _result;
    return Scaffold(
      appBar: AppBar(
        title: Text('Question ${_index + 1} / $total'),
        actions: [
          if (_remaining != null)
            Padding(
              padding: const EdgeInsets.only(right: 16),
              child: Center(child: Text('⏱️ ${_remaining}s', style: const TextStyle(fontSize: 18))),
            ),
        ],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(4),
          child: LinearProgressIndicator(value: (_index + (result != null ? 1 : 0)) / total),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(_question.prompt, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 16),
          _questionView(),
          if (result != null) ...[
            const SizedBox(height: 16),
            FeedbackCard(result: result),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _next,
              child: Text(_index + 1 >= total ? 'Voir mon bilan' : 'Question suivante'),
            ),
          ],
        ],
      ),
    );
  }
}
