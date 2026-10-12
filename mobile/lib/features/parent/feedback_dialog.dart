import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import 'parent_home_screen.dart';

/// « Donner mon avis » (tests en famille, étape 18) : une note et/ou quelques mots, lus
/// uniquement par l'équipe Ludifun.
Future<void> showFeedbackDialog(BuildContext context) async {
  final sent = await showDialog<bool>(context: context, builder: (_) => const FeedbackDialog());
  if (sent == true && context.mounted) {
    ScaffoldMessenger.of(context)
        .showSnackBar(const SnackBar(content: Text('Merci pour votre avis !')));
  }
}

class FeedbackDialog extends ConsumerStatefulWidget {
  const FeedbackDialog({super.key});

  static const maxLength = 1000;

  @override
  ConsumerState<FeedbackDialog> createState() => _FeedbackDialogState();
}

class _FeedbackDialogState extends ConsumerState<FeedbackDialog> {
  final _message = TextEditingController();
  int? _rating;
  bool _sending = false;

  @override
  void initState() {
    super.initState();
    _message.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _message.dispose();
    super.dispose();
  }

  bool get _ready => !_sending && (_rating != null || _message.text.trim().isNotEmpty);

  Future<void> _send() async {
    setState(() => _sending = true);
    final text = _message.text.trim();
    try {
      await ref
          .read(apiProvider)
          .sendFeedback(
            rating: _rating,
            message: text.isEmpty ? null : text,
            screen: 'parent_home',
          );
      if (mounted) Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _sending = false);
      showError(context, error);
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Donner mon avis'),
    content: SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Ludifun vous est-il utile ?'),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              for (var star = 1; star <= 5; star++)
                IconButton(
                  tooltip: '$star sur 5',
                  onPressed: () => setState(() => _rating = star),
                  icon: Icon(
                    star <= (_rating ?? 0) ? Icons.star_rounded : Icons.star_outline_rounded,
                    color: LudiColors.accent,
                    size: 34,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _message,
            maxLength: FeedbackDialog.maxLength,
            minLines: 3,
            maxLines: 6,
            decoration: const InputDecoration(
              labelText: 'Ce qui marche, ce qui manque, ce qui gêne…',
              border: OutlineInputBorder(),
            ),
          ),
          const Text(
            'Lu uniquement par l\'équipe Ludifun. N\'écrivez pas le nom de famille de votre enfant.',
            style: TextStyle(fontSize: 13),
          ),
        ],
      ),
    ),
    actions: [
      TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('Annuler')),
      FilledButton(onPressed: _ready ? _send : null, child: const Text('Envoyer')),
    ],
  );
}
