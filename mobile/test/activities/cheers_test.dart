import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ludifun/app/theme.dart';
import 'package:ludifun/features/session/cheers.dart';
import 'package:ludifun/features/session/correction_view.dart';
import 'package:ludifun/models/session.dart';

/// Point 4 : étoiles, série, confettis et secousse — pour le plaisir, jamais pour la note.
void main() {
  test('étoiles selon la réussite du jeu', () {
    expect([1.0, 0.8, 0.6, 0.59, 0.1, 0.0].map(starsFor), [3, 2, 2, 1, 1, 0]);
  });

  final item = SessionItem.fromJson({
    'id': 'i1',
    'type': 'MCQ',
    'block': 'core',
    'position': 1,
    'difficulty': 1,
    'knowledge_ids': ['k1'],
    'payload': {
      'prompt': 'Quand ?',
      'choices': [
        {'id': 'a', 'text': '1789'},
      ],
    },
  });

  Future<int> show(
    WidgetTester tester, {
    required String result,
    required double score,
    int streak = 0,
    bool calm = false,
  }) async {
    var stars = 0;
    await tester.pumpWidget(
      MaterialApp(
        theme: buildTheme(),
        home: MediaQuery(
          data: MediaQueryData(disableAnimations: calm),
          child: Scaffold(
            body: SingleChildScrollView(
              child: CorrectionView(
                item: item,
                correction: Correction.fromJson({'result': result, 'score': score}),
                stars: starsFor(score),
                streak: streak,
                onStar: () => stars++,
                onContinue: () {},
              ),
            ),
          ),
        ),
      ),
    );
    if (!calm) {
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.byType(CustomPaint), findsWidgets); // confettis ou secousse en cours
    }
    await tester.pumpAndSettle();
    return stars;
  }

  testWidgets('tout juste : 3 étoiles, une à une, et la série dès 3', (tester) async {
    expect(await show(tester, result: 'correct', score: 1, streak: 3), 3);
    expect(find.byKey(const Key('star-earned')), findsNWidgets(3));
    expect(find.text('🔥 3 bonnes réponses d\'affilée !'), findsOneWidget);
    expect(find.bySemanticsLabel('3 étoiles sur 3'), findsOneWidget);
  });

  testWidgets('presque : 2 étoiles ; pas tout à fait : aucune, pas de série', (tester) async {
    expect(await show(tester, result: 'partial', score: 0.7, streak: 0), 2);
    expect(find.byKey(const Key('star-earned')), findsNWidgets(2));
    expect(await show(tester, result: 'incorrect', score: 0, streak: 5), 0);
    expect(find.byKey(const Key('star-empty')), findsNWidgets(3));
    expect(find.textContaining('d\'affilée'), findsNothing);
  });

  testWidgets('animations réduites (réglage du téléphone) : étoiles tout de suite', (tester) async {
    expect(await show(tester, result: 'correct', score: 1, calm: true), 3);
    expect(find.byKey(const Key('star-earned')), findsNWidgets(3));
  });
}
