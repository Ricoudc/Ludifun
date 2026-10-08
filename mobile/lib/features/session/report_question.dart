import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/parent.dart';

/// « 🚩 Signaler un problème » sous la correction : l'enfant choisit une raison (rien à écrire),
/// le parent verra la question. Ni la note ni la progression ne changent.
class ReportQuestionButton extends ConsumerStatefulWidget {
  const ReportQuestionButton({required this.sessionId, required this.itemId, super.key});

  final String sessionId;
  final String itemId;

  @override
  ConsumerState<ReportQuestionButton> createState() => _ReportQuestionButtonState();
}

class _ReportQuestionButtonState extends ConsumerState<ReportQuestionButton> {
  bool _sending = false;
  bool _sent = false;

  Future<void> _report() async {
    final reason = await showModalBottomSheet<ReportReason>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Qu\'est-ce qui ne va pas ?', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 4),
              const Text(
                'Ton parent regardera cette question.',
                style: TextStyle(fontSize: 16, color: Colors.black54),
              ),
              const SizedBox(height: 12),
              for (final reason in ReportReason.values) ...[
                OutlinedButton(
                  onPressed: () => Navigator.of(context).pop(reason),
                  child: Align(alignment: Alignment.centerLeft, child: Text(reason.label)),
                ),
                const SizedBox(height: 8),
              ],
            ],
          ),
        ),
      ),
    );
    if (reason == null || !mounted) return;
    setState(() => _sending = true);
    String message;
    try {
      await ref.read(apiProvider).reportQuestion(widget.sessionId, widget.itemId, reason);
      message = 'Merci ! Ton parent va regarder cette question.';
      _sent = true;
    } on ApiException catch (error) {
      message = error.message;
    }
    if (!mounted) return;
    setState(() => _sending = false);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) => TextButton.icon(
    onPressed: _sending || _sent ? null : _report,
    style: TextButton.styleFrom(foregroundColor: Colors.black54),
    icon: const Icon(Icons.outlined_flag),
    label: Text(_sent ? 'Question signalée' : 'Signaler un problème'),
  );
}
