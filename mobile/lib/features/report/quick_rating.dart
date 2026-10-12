import 'package:flutter/material.dart';

/// « Tu as aimé cette séance ? » : trois visages, un seul toucher (tests en famille, étape 18).
///
/// Facultatif et discret : un échec d'envoi ne dérange pas l'enfant, on le remercie quand même.
class QuickRating extends StatefulWidget {
  const QuickRating({required this.onRate, super.key});

  final Future<void> Function(int rating) onRate;

  static const choices = [(1, '😕', 'Bof'), (3, '🙂', 'Bien'), (5, '😍', 'Génial')];

  @override
  State<QuickRating> createState() => _QuickRatingState();
}

class _QuickRatingState extends State<QuickRating> {
  bool _sent = false;

  Future<void> _rate(int rating) async {
    setState(() => _sent = true);
    try {
      await widget.onRate(rating);
    } on Exception {
      // Avis perdu : tant pis, la séance, elle, est bien enregistrée.
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_sent) {
      return const Text(
        'Merci ! 💜',
        textAlign: TextAlign.center,
        style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
      );
    }
    return Column(
      children: [
        const Text('Tu as aimé cette séance ?', style: TextStyle(fontSize: 18)),
        const SizedBox(height: 8),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            for (final (rating, face, label) in QuickRating.choices)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 6),
                child: Semantics(
                  button: true,
                  label: label,
                  excludeSemantics: true,
                  child: InkResponse(
                    onTap: () => _rate(rating),
                    radius: 32,
                    child: Padding(
                      padding: const EdgeInsets.all(8),
                      child: Text(face, style: const TextStyle(fontSize: 40)),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ],
    );
  }
}
