import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../support/screenshots.dart';

import 'package:ludifun/app/theme.dart';
import 'package:ludifun/features/session/activities/activity_registry.dart';
import 'package:ludifun/features/session/activities/figure_canvas.dart';
import 'package:ludifun/features/session/correction_view.dart';
import 'package:ludifun/models/account.dart';
import 'package:ludifun/models/figure.dart';
import 'package:ludifun/models/session.dart';

/// Étape 22 : carte et coloriage, sur une petite figure : deux régions côte à côte, un fleuve en
/// bas, une ville en haut à droite, un micro-État avec son repère.
final figure = Figure.fromJson({
  'id': 'test',
  'version': 1,
  'title': 'Figure de test',
  'credits': 'Ludifun',
  'width': 200,
  'height': 100,
  'decor': [
    {
      'kind': 'area',
      'shapes': [
        [
          [0, 0, 200, 0, 200, 100, 0, 100],
        ],
      ],
      'fill': '#d6e6f5',
      'stroke': null,
      'width': 1,
    },
  ],
  'zones': [
    {
      'id': 'ouest',
      'name': 'Ouest',
      'kind': 'area',
      'shapes': [
        [
          [0, 0, 100, 0, 100, 80, 0, 80],
        ],
      ],
    },
    {
      'id': 'est',
      'name': 'Est',
      'kind': 'area',
      'shapes': [
        [
          [100, 0, 200, 0, 200, 80, 100, 80],
          [140, 30, 160, 30, 160, 50, 140, 50], // un lac : un trou
        ],
      ],
    },
    {
      'id': 'mini',
      'name': 'Mini',
      'kind': 'area',
      'shapes': [
        [
          [60, 40, 61, 40, 61, 41, 60, 41],
        ],
      ],
      'marker': [60.5, 40.5, 6],
    },
    {
      'id': 'fleuve',
      'name': 'Fleuve',
      'kind': 'line',
      'shapes': [
        [
          [0, 90, 200, 90],
        ],
      ],
    },
    {
      'id': 'ville',
      'name': 'Ville',
      'kind': 'point',
      'shapes': [
        [
          [180, 15, 190, 20, 180, 25, 170, 20],
        ],
      ],
    },
  ],
  'labels': [
    {'text': '1789', 'x': 100, 'y': 95, 'size': 8},
  ],
});

void main() {
  test('trouver la zone touchée : points et traits d\'abord, trous et repères compris', () {
    expect(figure.hit(const Offset(20, 20), 5)?.id, 'ouest');
    expect(figure.hit(const Offset(120, 20), 5)?.id, 'est');
    expect(figure.hit(const Offset(150, 40), 5), isNull); // dans le lac
    expect(figure.hit(const Offset(50, 88), 5)?.id, 'fleuve');
    expect(figure.hit(const Offset(183, 21), 5)?.id, 'ville');
    expect(figure.hit(const Offset(63, 43), 5)?.id, 'mini'); // repère du micro-État
    expect(parseColor('#e5484d'), const Color(0xFFE5484D));
    expect(parseColor('rouge'), isNull);
  });

  test('les figures du serveur se lisent et se touchent', () {
    final files = Directory('../backend/app/figures').listSync().whereType<File>().toList();
    expect(files, hasLength(12));
    for (final file in files) {
      final real = Figure.fromJson(jsonDecode(file.readAsStringSync()) as Json);
      expect(real.zones, isNotEmpty, reason: real.id);
    }
    final regions = Figure.fromJson(
      jsonDecode(File('../backend/app/figures/france-regions.json').readAsStringSync()) as Json,
    );
    final bretagne = regions.zone('bretagne')!.paths.first.getBounds().center;
    expect(regions.hit(bretagne, 5)?.name, 'Bretagne');
  });

  Future<List<Json>> show(WidgetTester tester, String type, Json payload) async {
    final sent = <Json>[];
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.5;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [figureProvider.overrideWith((ref, id) async => figure)],
        child: MaterialApp(
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
    await shot(tester, 'a_$type');
    return sent;
  }

  Future<void> touch(WidgetTester tester, Offset point) async {
    final canvas = find.byKey(const ValueKey('figure-canvas'));
    final rect = tester.getRect(canvas);
    await tester.tapAt(rect.topLeft + point * (rect.width / figure.size.width));
    await tester.pump();
  }

  testWidgets('carte : un nom à la fois, annuler, envoi au dernier', (tester) async {
    final sent = await show(tester, 'MAP', {
      'prompt': 'Figure de test : touche sur le dessin chaque nom demandé.',
      'figure': {'id': 'test', 'version': 1},
      'items': [
        {'id': 'q1', 'text': 'Est'},
        {'id': 'q2', 'text': 'Fleuve'},
      ],
    });
    expect(find.text('Touche : Est  (1 / 2)'), findsOneWidget);
    await touch(tester, const Offset(20, 20)); // Ouest : erreur
    expect(find.text('Touche : Fleuve  (2 / 2)'), findsOneWidget);
    await tester.tap(find.text('Annuler'));
    await tester.pump();
    await touch(tester, const Offset(120, 20));
    await touch(tester, const Offset(10, 90));
    expect(sent, [
      {
        'answers': [
          ['q1', 'est'],
          ['q2', 'fleuve'],
        ],
      },
    ]);
  });

  testWidgets('coloriage : choisir une couleur, colorier, effacer, finir', (tester) async {
    final sent = await show(tester, 'COLORING', {
      'prompt': 'Colorie le dessin selon la légende : les régions',
      'figure': {'id': 'test', 'version': 1},
      'palette': [
        {'id': 'p1', 'name': 'Au bord de la mer', 'color': '#e5484d', 'color_name': 'rouge'},
        {'id': 'p2', 'name': 'Dans les terres', 'color': '#3d7cc9', 'color_name': 'bleu'},
      ],
      'count': 2,
    });
    expect(find.text('Encore 2 à colorier'), findsOneWidget);
    await touch(tester, const Offset(20, 20)); // rouge
    await touch(tester, const Offset(120, 20)); // rouge…
    await touch(tester, const Offset(120, 20)); // … effacé
    await tester.tap(find.text('Dans les terres'));
    await tester.pump();
    await touch(tester, const Offset(120, 20)); // bleu
    await tester.tap(find.text('J\'ai fini'));
    await tester.pump();
    expect(sent, [
      {
        'colors': [
          ['ouest', 'p1'],
          ['est', 'p2'],
        ],
      },
    ]);
  });

  testWidgets('correction de la carte : le dessin, et la zone touchée à tort', (tester) async {
    final item = SessionItem.fromJson({
      'id': 'i1',
      'position': 0,
      'block': 'match',
      'type': 'MAP',
      'difficulty': 2,
      'knowledge_ids': ['k1', 'k2'],
      'payload': {
        'prompt': 'Figure de test',
        'figure': {'id': 'test', 'version': 1},
        'items': [
          {'id': 'q1', 'text': 'Est'},
          {'id': 'q2', 'text': 'Fleuve'},
        ],
      },
      'help_available': false,
      'attempt': null,
    });
    final correction = Correction.fromJson({
      'item_id': 'i1',
      'result': 'partial',
      'score': 0.5,
      'correct_answer': 'Regarde où se trouve chaque nom sur le dessin.',
      'details': [
        {'id': 'q1', 'correct': false, 'zone': 'est', 'touched': 'ouest', 'touched_name': 'Ouest'},
        {
          'id': 'q2',
          'correct': true,
          'zone': 'fleuve',
          'touched': 'fleuve',
          'touched_name': 'Fleuve',
        },
      ],
    });
    await tester.pumpWidget(
      ProviderScope(
        overrides: [figureProvider.overrideWith((ref, id) async => figure)],
        child: MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: CorrectionView(item: item, correction: correction, onContinue: () {}),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Est (tu as touché : Ouest)'), findsOneWidget);
    expect(find.text('Fleuve'), findsOneWidget);
    final canvas = tester.widget<FigureCanvas>(find.byType(FigureCanvas));
    expect(canvas.colors, {
      'ouest': LudiColors.notMastered,
      'est': LudiColors.toReview,
      'fleuve': LudiColors.mastered,
    });
  });
}
