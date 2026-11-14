import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ludifun/app/theme.dart';
import 'package:ludifun/features/report/report_view.dart';
import 'package:ludifun/models/session.dart';

/// §5.98 : duel contre soi, dans le bilan.
void main() {
  Report report(Object? previous) => Report.fromJson({
    'session_id': 's1',
    'score_on_10': 8,
    'counts': <String, int>{},
    'knowledge': <Object>[],
    'next_review_at': null,
    'lesson_mastered': false,
    'can_review_errors': false,
    'previous_score_on_10': ?previous,
  });

  Future<void> show(WidgetTester tester, Report r) => tester.pumpWidget(
    MaterialApp(
      theme: buildTheme(),
      home: Scaffold(
        body: SingleChildScrollView(child: ReportView(report: r)),
      ),
    ),
  );

  test('la phrase suit la comparaison, sans jamais gronder', () {
    expect(selfDuel(8, 6.5), '🏆 Tu as battu ta dernière note (6,5 / 10) !');
    expect(selfDuel(8, 8), '🤝 Égalité avec ta dernière fois (8 / 10).');
    expect(selfDuel(5, 8), '🎯 La dernière fois : 8 / 10. Tu la battras la prochaine fois !');
  });

  testWidgets('le bilan montre la note à battre', (tester) async {
    await show(tester, report(6));
    expect(find.byKey(const ValueKey('self-duel')), findsOneWidget);
    expect(find.textContaining('Tu as battu ta dernière note'), findsOneWidget);
  });

  testWidgets('première séance ou serveur d\'avant : pas de duel', (tester) async {
    await show(tester, report(null));
    expect(find.byKey(const ValueKey('self-duel')), findsNothing);
  });
}
