import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ludifun/app/api_image.dart';
import 'package:ludifun/app/theme.dart';
import 'package:ludifun/features/session/activities/activity_registry.dart';

import '../support/fakes.dart';

/// Apprendre par l'image (étape 28) : les images viennent du serveur, sans légende.
void main() {
  late List<Map<String, Object?>> sent;
  late List<String> loaded;
  setUp(() {
    sent = [];
    loaded = [];
  });

  Future<void> show(WidgetTester tester, String type, Map<String, Object?> payload) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.5;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          imageBytesProvider.overrideWith((ref, path) async {
            loaded.add(path);
            return tinyPng;
          }),
        ],
        child: MaterialApp(
          theme: buildTheme(),
          home: Scaffold(
            body: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: activityRegistry[type]!(payload, sent.add),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  const pictures = [
    {'id': 'p1', 'image': '/v1/lessons/l1/images/a'},
    {'id': 'p2', 'image': '/v1/lessons/l1/images/b'},
    {'id': 'p3', 'image': '/v1/lessons/l1/images/c'},
  ];

  testWidgets('image et mot : toucher une image puis son mot les relie', (tester) async {
    await show(tester, 'PICTURE_MATCH', {
      'prompt': 'Relie chaque image au mot qui lui correspond.',
      'pictures': pictures,
      'words': [
        {'id': 'w1', 'text': 'Volcan'},
        {'id': 'w2', 'text': 'Chenille'},
        {'id': 'w3', 'text': 'Château fort'},
      ],
    });
    expect(loaded.toSet(), {for (final p in pictures) p['image']});
    expect(find.text('Encore 3 image(s) à relier'), findsOneWidget);
    await tester.tap(find.bySemanticsLabel('Image 1'));
    await tester.tap(find.text('Chenille'));
    await tester.pump();
    // Un mot puis une image marche aussi.
    await tester.tap(find.text('Volcan'));
    await tester.tap(find.bySemanticsLabel('Image 2'));
    await tester.pump();
    // Toucher une image reliée la détache.
    await tester.tap(find.bySemanticsLabel('Image 2'));
    await tester.pump();
    expect(find.text('Encore 2 image(s) à relier'), findsOneWidget);
    await tester.tap(find.bySemanticsLabel('Image 2'));
    await tester.tap(find.text('Château fort'));
    await tester.tap(find.bySemanticsLabel('Image 3'));
    await tester.tap(find.text('Volcan'));
    await tester.pump();
    await tester.tap(find.text('Valider'));
    expect(sent, [
      {
        'pairs': [
          ['p1', 'w2'],
          ['p2', 'w3'],
          ['p3', 'w1'],
        ],
      },
    ]);
  });

  testWidgets('quelle image ? : une phrase à la fois, l\'image choisie disparaît', (tester) async {
    await show(tester, 'PICTURE_FIND', {
      'prompt': 'Lis la phrase, puis touche l\'image qui la montre.',
      'pictures': pictures,
      'clues': [
        {'id': 'c1', 'text': 'La chenille devient un papillon.'},
        {'id': 'c2', 'text': 'Le volcan crache de la lave.'},
        {'id': 'c3', 'text': 'Le château fort protège le seigneur.'},
      ],
    });
    expect(find.text('🖼️ Quelle image ? · 1/3'), findsOneWidget);
    expect(find.text('La chenille devient un papillon.'), findsOneWidget);
    await tester.tap(find.bySemanticsLabel('Image 2'));
    await tester.pumpAndSettle();
    expect(find.text('Le volcan crache de la lave.'), findsOneWidget);
    expect(find.bySemanticsLabel('Image 2'), findsNothing);
    await tester.tap(find.bySemanticsLabel('Image 1'));
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel('Image 3'));
    await tester.pumpAndSettle();
    expect(sent, [
      {
        'answers': [
          ['c1', 'p2'],
          ['c2', 'p1'],
          ['c3', 'p3'],
        ],
      },
    ]);
    expect(find.text('Bravo, c\'est fini !'), findsOneWidget);
  });
}
