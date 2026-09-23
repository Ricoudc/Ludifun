import 'package:flutter/material.dart';

import '../api/models.dart';

const statusStyle = {
  'acquis': ('🟢', 'acquis'),
  'a_renforcer': ('🟠', 'à renforcer'),
  'a_revoir': ('🔴', 'à revoir'),
};

/// Écran 5 : bilan de la séance.
class ResultScreen extends StatelessWidget {
  final SessionReport report;
  const ResultScreen({super.key, required this.report});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final score = report.scoreOn10 == report.scoreOn10.roundToDouble()
        ? report.scoreOn10.toStringAsFixed(0)
        : report.scoreOn10.toStringAsFixed(1);
    return Scaffold(
      appBar: AppBar(title: const Text('Mon bilan'), automaticallyImplyLeading: false),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          Text(report.message, style: theme.textTheme.headlineSmall, textAlign: TextAlign.center),
          const SizedBox(height: 16),
          Text('$score / 10', style: theme.textTheme.displayMedium, textAlign: TextAlign.center),
          Text('${report.correct} bonne(s) réponse(s) sur ${report.answered}', textAlign: TextAlign.center),
          const SizedBox(height: 24),
          for (final n in report.notions)
            ListTile(
              leading: Text(statusStyle[n.status]!.$1, style: const TextStyle(fontSize: 22)),
              title: Text(n.label),
              trailing: Text(statusStyle[n.status]!.$2),
            ),
          const SizedBox(height: 24),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Padding(padding: EdgeInsets.all(12), child: Text('Retour à la leçon')),
          ),
        ],
      ),
    );
  }
}
