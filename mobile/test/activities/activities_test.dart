import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../support/screenshots.dart';

import 'package:ludifun/app/theme.dart';
import 'package:ludifun/features/session/activities/activity_registry.dart';
import 'package:ludifun/features/session/activities/alignment_view.dart';
import 'package:ludifun/features/session/activities/math_games_views.dart';
import 'package:ludifun/core/speech.dart';
import 'package:ludifun/features/session/activities/common.dart';
import 'package:ludifun/features/session/activities/dictation_view.dart';
import 'package:ludifun/features/session/correction_view.dart';
import 'package:ludifun/models/session.dart';

class FakeSpeaker implements Speaker {
  FakeSpeaker({this.voice = true});

  final bool voice;
  final said = <String>[];

  @override
  Future<bool> speak(String text) async {
    said.add(text);
    return voice;
  }

  @override
  Future<void> stop() async {}
}

/// Chaque widget d'activité produit la réponse attendue par l'API (§7.3).
void main() {
  late List<Map<String, Object?>> sent;
  setUp(() => sent = []);

  Future<void> show(
    WidgetTester tester,
    String type,
    Map<String, Object?> payload, {
    String? instruction,
  }) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.5;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        theme: buildTheme(),
        home: Scaffold(
          body: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: ActivityInstruction(
              text: instruction,
              child: activityRegistry[type]!(payload, sent.add),
            ),
          ),
        ),
      ),
    );
    await shot(tester, 'a_$type');
  }

  testWidgets('QCM tiré d\'un site de confiance : la source est affichée', (tester) async {
    await show(tester, 'MCQ', {
      'prompt': 'Quel animal vertébré vit dans la mer ?',
      'source': 'fr.vikidia.org',
      'choices': [
        {'id': 'a', 'text': 'La baleine'},
        {'id': 'b', 'text': 'La méduse'},
        {'id': 'c', 'text': 'Le ver de terre'},
        {'id': 'd', 'text': 'L\'escargot'},
      ],
    });
    expect(find.text('📚 En plus de ta leçon — d\'après fr.vikidia.org'), findsOneWidget);
    await tester.tap(find.text('La baleine'));
    expect(sent, [
      {'choice_id': 'a'},
    ]);
  });

  testWidgets('QCM : un seul choix, envoyé aussitôt', (tester) async {
    await show(tester, 'MCQ', {
      'prompt': 'En quelle année commence la Révolution ?',
      'choices': [
        {'id': 'a', 'text': '1492'},
        {'id': 'b', 'text': '1789'},
      ],
    });
    expect(find.text('En quelle année commence la Révolution ?'), findsOneWidget);
    await tester.tap(find.text('1789'));
    await tester.tap(find.text('1492')); // trop tard
    expect(sent, [
      {'choice_id': 'b'},
    ]);
  });

  testWidgets('QCM sur un texte lu : le passage à relire est affiché', (tester) async {
    await show(tester, 'MCQ', {
      'prompt': 'Dans ce passage, que porte le Petit Chaperon rouge ?',
      'passage': 'Elle part avec une galette et un petit pot de beurre.',
      'choices': [
        {'id': 'a', 'text': 'une galette'},
        {'id': 'b', 'text': 'des fleurs'},
      ],
    });
    expect(find.text('📖 Elle part avec une galette et un petit pot de beurre.'), findsOneWidget);
    expect(find.text('Dans ce passage, que porte le Petit Chaperon rouge ?'), findsOneWidget);
  });

  testWidgets('🔊 la consigne, la question et les choix lus à voix haute', (tester) async {
    final speaker = FakeSpeaker();
    ListenButton.speakerFactory = () => speaker;
    addTearDown(() => ListenButton.speakerFactory = PhoneSpeaker.new);
    await show(tester, 'MCQ', {
      'prompt': 'Combien font 7 + 8 ? 🤔',
      'choices': [
        {'id': 'a', 'text': '15'},
        {'id': 'b', 'text': '16'},
      ],
    }, instruction: 'Touche la bonne réponse');
    await tester.tap(find.byTooltip('Écouter'));
    await tester.pumpAndSettle();
    expect(speaker.said, ['Touche la bonne réponse. Combien font 7 + 8 ? A : 15. B : 16.']);
    expect(sent, isEmpty); // écouter ne répond pas
  });

  testWidgets('🔊 sans voix française : on le dit, et un trou se lit comme une pause', (
    tester,
  ) async {
    final speaker = FakeSpeaker(voice: false);
    ListenButton.speakerFactory = () => speaker;
    addTearDown(() => ListenButton.speakerFactory = PhoneSpeaker.new);
    await show(tester, 'FILL_BLANK', {'text': 'La Révolution commence en ___.'});
    await tester.tap(find.byTooltip('Écouter'));
    await tester.pumpAndSettle();
    expect(speaker.said.single, endsWith('La Révolution commence en ….'));
    expect(
      find.text('Ce téléphone n\'a pas de voix française : demande à un adulte de lire.'),
      findsOneWidget,
    );
  });

  test('texte lu : sans émojis, ponctuation ajoutée', () {
    expect(spokenText(['🗺️ Carte', '', 'Où est Paris ?']), 'Carte. Où est Paris ?');
  });

  testWidgets('points alignés : toucher les points, en retirer un, valider', (tester) async {
    await show(tester, 'ALIGN', {
      'prompt': 'Touche les 4 clous alignés.',
      'task': 'select',
      'shape': 'nail',
      'count': 4,
      'points': [
        for (final (id, x, y) in [
          ('A', 2, 2),
          ('B', 5, 5),
          ('C', 8, 8),
          ('D', 11, 11),
          ('E', 14, 3),
          ('F', 20, 6),
          ('G', 18, 12),
        ])
          {'id': id, 'x': x, 'y': y, 'color': 'black'},
      ],
    });
    final figure = find.byType(AlignmentFigure);
    final box = tester.getRect(figure);
    final scale = box.width / 26;
    Future<void> touch(int x, int y) async {
      await tester.tapAt(box.topLeft + Offset((x + 1) * scale, (y + 1) * scale));
      await tester.pump();
    }

    expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed, isNull);
    for (final (x, y) in [(2, 2), (5, 5), (14, 3), (8, 8), (11, 11)]) {
      await touch(x, y);
    }
    await touch(14, 3); // E retiré
    expect(find.text('Points touchés : 4 / 4'), findsOneWidget);
    await tester.tap(find.text('Valider'));
    expect(sent, [
      {
        'selected': ['A', 'B', 'C', 'D'],
      },
    ]);
  });

  testWidgets('droite graduée : toucher une graduation, valider', (tester) async {
    await show(tester, 'NUMBER_LINE', {
      'prompt': 'Touche la graduation du nombre 3/4.',
      'task': 'place',
      'intervals': 4,
      'labels': [
        {'index': 0, 'text': '0'},
        {'index': 4, 'text': '1'},
      ],
    });
    final line = tester.getRect(find.byKey(const Key('number-line')));
    final step = (line.width - 48) / 4;
    await tester.tapAt(Offset(line.left + 24 + 3 * step, line.center.dy));
    await tester.pump();
    await tester.tap(find.text('Valider'));
    expect(sent, [
      {'index': 3},
    ]);
  });

  testWidgets('droite graduée : lire le nombre de la flèche', (tester) async {
    await show(tester, 'NUMBER_LINE', {
      'prompt': 'Quel nombre montre la flèche ?',
      'task': 'read',
      'intervals': 10,
      'arrow': 7,
      'labels': [
        {'index': 0, 'text': '2'},
        {'index': 10, 'text': '3'},
      ],
      'choices': [
        {'id': 'a', 'text': '2,7'},
        {'id': 'b', 'text': '2,6'},
        {'id': 'c', 'text': '7'},
        {'id': 'd', 'text': '2,8'},
      ],
    });
    await tester.tap(find.text('2,7'));
    expect(sent, [
      {'choice_id': 'a'},
    ]);
  });

  testWidgets('fraction à colorier : toucher les parts de la bande', (tester) async {
    await show(tester, 'FRACTION_BAR', {
      'prompt': 'Colorie les 2/5 de la bande.',
      'task': 'color',
      'shape': 'bar',
      'parts': 5,
    });
    final bar = tester.getRect(find.byKey(const Key('fraction-shape')));
    final part = bar.width / 5;
    for (final i in [4, 1, 2]) {
      await tester.tapAt(Offset(bar.left + (i + 0.5) * part, bar.center.dy));
      await tester.pump();
    }
    await tester.tapAt(Offset(bar.left + 2.5 * part, bar.center.dy)); // décolorier
    await tester.pump();
    expect(find.text('Parts coloriées : 2 sur 5'), findsOneWidget);
    await tester.tap(find.text('Valider'));
    expect(sent, [
      {
        'colored': [1, 4],
      },
    ]);
  });

  testWidgets('fraction à colorier : lire la fraction du disque', (tester) async {
    await show(tester, 'FRACTION_BAR', {
      'prompt': 'Quelle fraction du disque est coloriée ?',
      'task': 'read',
      'shape': 'disc',
      'parts': 6,
      'colored': [0, 1],
      'choices': [
        {'id': 'a', 'text': '2/6'},
        {'id': 'b', 'text': '6/2'},
        {'id': 'c', 'text': '4/6'},
        {'id': 'd', 'text': '2/4'},
      ],
    });
    await tester.tap(find.text('2/6'));
    expect(sent, [
      {'choice_id': 'a'},
    ]);
  });

  testWidgets('opération posée : écrire de droite à gauche, effacer, valider', (tester) async {
    await show(tester, 'COLUMN_OP', {
      'prompt': 'Pose et calcule : 347 + 285',
      'operator': '+',
      'operands': ['347', '285'],
      'boxes': 4,
    });
    expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed, isNull);
    for (final digit in ['2', '3', '9']) {
      await tester.tap(find.widgetWithText(OutlinedButton, digit));
      await tester.pump();
    }
    await tester.tap(find.byIcon(Icons.backspace_outlined)); // le 9 retiré
    await tester.pump();
    await tester.tap(find.widgetWithText(OutlinedButton, '6'));
    await tester.pump();
    await tester.ensureVisible(find.text('Valider'));
    await tester.tap(find.text('Valider'));
    expect(sent, [
      {'result': '632'},
    ]);
  });

  testWidgets('chasse aux mots : toucher, retirer, valider', (tester) async {
    await show(tester, 'WORD_HUNT', {
      'prompt': 'Touche tous les noms.',
      'words': [
        {'id': 'w1', 'text': 'chat'},
        {'id': 'w2', 'text': 'courir'},
        {'id': 'w3', 'text': 'maison'},
        {'id': 'w4', 'text': 'rouge'},
      ],
    });
    for (final word in ['maison', 'courir', 'chat', 'courir']) {
      await tester.tap(find.text(word));
      await tester.pump();
    }
    await tester.tap(find.text('Valider'));
    expect(sent, [
      {
        'selected': ['w1', 'w3'],
      },
    ]);
  });

  testWidgets('conjugaison : remplir les lignes, en vider une, valider', (tester) async {
    await show(tester, 'CONJUGATION', {
      'prompt': 'Conjugue « finir » au présent.',
      'word': 'finir',
      'items': [
        {'id': 'p0', 'text': 'je'},
        {'id': 'p1', 'text': 'tu'},
        {'id': 'p2', 'text': 'il'},
      ],
      'choices': [
        {'id': 'c1', 'text': 'finit'},
        {'id': 'c2', 'text': 'finis'},
        {'id': 'c3', 'text': 'finis'},
      ],
    });
    await tester.tap(find.text('finit')); // je → finit (erreur)
    await tester.pump();
    await tester.tap(find.text('finit')); // la ligne se vide
    await tester.pump();
    await tester.tap(find.text('finis').first);
    await tester.pump();
    await tester.tap(find.text('finis').last);
    await tester.pump();
    await tester.tap(find.text('finit'));
    await tester.pump();
    await tester.tap(find.text('Valider'));
    expect(sent, [
      {
        'answers': [
          ['p0', 'c2'],
          ['p1', 'c3'],
          ['p2', 'c1'],
        ],
      },
    ]);
  });

  testWidgets('bon pronom : la case avant la forme, chaque pronom une fois', (tester) async {
    await show(tester, 'PRONOUN', {
      'prompt': 'Trouve le bon pronom : verbe « aller » au présent.',
      'word': 'aller',
      'blank_first': true,
      'items': [
        {'id': 'p3', 'text': 'allons'},
        {'id': 'p5', 'text': 'vont'},
      ],
      'choices': [
        {'id': 'c1', 'text': 'ils'},
        {'id': 'c2', 'text': 'nous'},
        {'id': 'c3', 'text': 'je'},
      ],
    });
    // La case est à gauche de la forme.
    final box = tester.getTopLeft(find.text('allons'));
    await tester.tap(find.text('nous'));
    await tester.pump();
    expect(tester.getTopLeft(find.text('nous')).dx, lessThan(box.dx));
    await tester.tap(find.text('ils'));
    await tester.pump();
    await tester.tap(find.text('Valider'));
    expect(sent, [
      {
        'answers': [
          ['p3', 'c2'],
          ['p5', 'c1'],
        ],
      },
    ]);
  });

  testWidgets('synonymes et familles de mots : écrans de l\'association et des homophones', (
    tester,
  ) async {
    await show(tester, 'WORD_FAMILY', {
      'prompt': 'Trouve le mot de la même famille.',
      'items': [
        {
          'id': 's1',
          'text': '« boxeur » est de la même famille que ___.',
          'choices': ['boîte', 'boxe', 'fleur', 'lait'],
        },
      ],
    });
    await tester.tap(find.text('boxe'));
    await tester.pump();
    expect(sent, [
      {
        'answers': [
          ['s1', 'boxe'],
        ],
      },
    ]);
    expect(activityRegistry.containsKey('SYNONYMS'), isTrue);
    expect(activityRegistry.containsKey('PRONOUN'), isTrue);
  });

  testWidgets('homophones : une phrase à la fois, réponse après la dernière', (tester) async {
    await show(tester, 'HOMOPHONE', {
      'prompt': 'Choisis le bon mot pour chaque phrase.',
      'items': [
        {
          'id': 's1',
          'text': 'Léa ___ un chat.',
          'choices': ['a', 'à'],
        },
        {
          'id': 's2',
          'text': 'Je vais ___ l\'école.',
          'choices': ['a', 'à'],
        },
      ],
    });
    expect(find.text('Phrase 1 sur 2'), findsOneWidget);
    await tester.tap(find.text('a'));
    await tester.pump();
    expect(sent, isEmpty);
    expect(find.text('Phrase 2 sur 2'), findsOneWidget);
    await tester.tap(find.text('à'));
    await tester.pump();
    expect(sent, [
      {
        'answers': [
          ['s1', 'a'],
          ['s2', 'à'],
        ],
      },
    ]);
  });

  testWidgets('lire l\'heure : choisir l\'heure de l\'horloge', (tester) async {
    await show(tester, 'CLOCK', {
      'prompt': 'Quelle heure est-il ?',
      'hour': 3,
      'minute': 15,
      'choices': [
        {'id': 'a', 'text': '3 h 15'},
        {'id': 'b', 'text': '3 h 03'},
        {'id': 'c', 'text': '4 h 15'},
        {'id': 'd', 'text': '3 h 45'},
      ],
    });
    await tester.tap(find.text('3 h 15'));
    await tester.tap(find.text('3 h 45')); // une seule réponse
    expect(sent, [
      {'choice_id': 'a'},
    ]);
  });

  testWidgets('monnaie : toucher les pièces pour payer juste', (tester) async {
    await show(tester, 'MONEY', {
      'prompt': 'Touche les pièces et les billets pour payer 7 €.',
      'task': 'pay',
      'items': [
        {'id': 'm1', 'value': 500},
        {'id': 'm2', 'value': 200},
        {'id': 'm3', 'value': 100},
      ],
    });
    for (final id in ['m1', 'm3', 'm2', 'm3']) {
      await tester.tap(find.byKey(Key('piece-$id')));
      await tester.pump();
    }
    expect(find.text('Tu donnes : 7 €'), findsOneWidget);
    await tester.tap(find.text('Payer'));
    expect(sent, [
      {
        'selected': ['m1', 'm2'],
      },
    ]);
  });

  testWidgets('règle : lire la longueur du segment', (tester) async {
    await show(tester, 'RULER', {
      'prompt': 'Combien mesure le segment rouge ?',
      'ruler_cm': 15,
      'start_mm': 20,
      'length_mm': 53,
      'choices': [
        {'id': 'a', 'text': '7 cm 3 mm'},
        {'id': 'b', 'text': '5 cm 3 mm'},
        {'id': 'c', 'text': '53 cm'},
        {'id': 'd', 'text': '3 cm 5 mm'},
      ],
    });
    expect(find.byKey(const Key('ruler')), findsOneWidget);
    await tester.tap(find.text('5 cm 3 mm'));
    await tester.tap(find.text('53 cm')); // une seule réponse
    expect(sent, [
      {'choice_id': 'b'},
    ]);
  });

  testWidgets('symétrie : toucher les cases de l\'autre côté, en retirer une, valider', (
    tester,
  ) async {
    await show(tester, 'SYMMETRY', {
      'prompt': 'Complète la figure par symétrie : touche les cases à droite de l\'axe.',
      'width': 10,
      'height': 8,
      'axis': 'vertical',
      'filled': [
        [4, 2],
        [3, 2],
        [4, 3],
      ],
    });
    final grid = tester.getRect(find.byKey(const Key('symmetry-grid')));
    final side = grid.width / 10;
    Future<void> touch(int x, int y) async {
      await tester.tapAt(grid.topLeft + Offset((x + 0.5) * side, (y + 0.5) * side));
      await tester.pump();
    }

    expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed, isNull);
    await touch(1, 1); // côté déjà dessiné : rien
    for (final (x, y) in [(5, 2), (6, 2), (7, 7), (5, 3), (7, 7)]) {
      await touch(x, y);
    }
    expect(find.text('Cases coloriées : 3'), findsOneWidget);
    await tester.tap(find.text('Valider'));
    expect(sent, [
      {
        'selected': [
          [5, 2],
          [5, 3],
          [6, 2],
        ],
      },
    ]);
  });

  testWidgets('syllabes : couper chaque mot, un mot à la fois', (tester) async {
    await show(tester, 'SYLLABLES', {
      'prompt': 'Coupe chaque mot en syllabes.',
      'items': [
        {'id': 'w1', 'text': 'vélo'},
        {'id': 'w2', 'text': 'domino'},
      ],
    });
    expect(find.text('Mot 1 sur 2'), findsOneWidget);
    await tester.tap(find.byKey(const Key('gap-3')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('gap-3'))); // retirée
    await tester.tap(find.byKey(const Key('gap-2')));
    await tester.pump();
    expect(find.text('vé-lo'), findsOneWidget);
    await tester.tap(find.text('Mot suivant'));
    await tester.pump();
    expect(sent, isEmpty);
    expect(find.text('Mot 2 sur 2'), findsOneWidget);
    for (final gap in [2, 4]) {
      await tester.tap(find.byKey(Key('gap-$gap')));
      await tester.pump();
    }
    expect(find.text('do-mi-no'), findsOneWidget);
    await tester.tap(find.text('Valider'));
    await tester.pump();
    expect(sent, [
      {
        'answers': [
          [
            'w1',
            [2],
          ],
          [
            'w2',
            [2, 4],
          ],
        ],
      },
    ]);
  });

  test('monnaie : écriture des sommes', () {
    expect(
      [moneyLabel(5), moneyLabel(230), moneyLabel(1205), moneyLabel(2000)],
      ['5 c', '2,30 €', '12,05 €', '20 €'],
    );
  });

  testWidgets('points alignés : oui ou non', (tester) async {
    await show(tester, 'ALIGN', {
      'prompt': 'Les 3 points sont-ils alignés ?',
      'task': 'yes_no',
      'points': [
        {'id': 'A', 'x': 2, 'y': 2, 'color': 'black'},
        {'id': 'B', 'x': 6, 'y': 4, 'color': 'black'},
        {'id': 'C', 'x': 10, 'y': 6, 'color': 'black'},
      ],
      'choices': [
        {'id': 'oui', 'text': 'Oui'},
        {'id': 'non', 'text': 'Non'},
      ],
    });
    await tester.tapAt(tester.getCenter(find.byType(AlignmentFigure))); // la figure ne répond pas
    await tester.tap(find.text('Oui'));
    expect(sent, [
      {'choice_id': 'oui'},
    ]);
  });

  testWidgets('démêler : toucher les mots dans l\'ordre', (tester) async {
    await show(tester, 'UNJUMBLE', {
      'prompt': 'Remets les mots dans l\'ordre.',
      'words': [
        {'id': 'w2', 'text': 'chat'},
        {'id': 'w1', 'text': 'Le'},
        {'id': 'w3', 'text': 'dort.'},
      ],
    });
    await tester.tap(find.text('Le'));
    await tester.tap(find.text('chat'));
    await tester.pump();
    expect(find.text('Encore 1 mot(s)'), findsOneWidget);
    await tester.tap(find.text('dort.'));
    await tester.pump();
    await tester.tap(find.text('Valider'));
    expect(sent, [
      {
        'order': ['w1', 'w2', 'w3'],
      },
    ]);
  });

  testWidgets('trouver la correspondance : un indice à la fois', (tester) async {
    await show(tester, 'FIND_MATCH', {
      'targets': [
        {'id': 't1', 'text': 'Clovis'},
        {'id': 't2', 'text': 'Charlemagne'},
      ],
      'clues': [
        {'id': 'c1', 'text': 'Empereur en 800'},
        {'id': 'c2', 'text': 'Roi des Francs baptisé'},
      ],
    });
    expect(find.text('Empereur en 800'), findsOneWidget);
    await tester.tap(find.text('Charlemagne'));
    await tester.pump();
    expect(find.text('Roi des Francs baptisé'), findsOneWidget);
    expect(find.text('Charlemagne'), findsNothing); // déjà choisie
    await tester.tap(find.text('Clovis'));
    await tester.pump();
    expect(sent, [
      {
        'answers': [
          ['c1', 't2'],
          ['c2', 't1'],
        ],
      },
    ]);
  });

  testWidgets('roue aléatoire : tourner, répondre, trois fois', (tester) async {
    Map<String, Object?> spin(String id, String segment) => {
      'id': id,
      'segment': segment,
      'prompt': 'Question $id ?',
      'choices': [
        {'id': 'a', 'text': 'Réponse A $id'},
        {'id': 'b', 'text': 'Réponse B $id'},
      ],
    };
    await show(tester, 'WHEEL', {
      'segments': [
        {'id': 's0', 'text': '🍎'},
        {'id': 's1', 'text': '🚀'},
        {'id': 's2', 'text': '⭐'},
      ],
      'spins': [spin('q1', 's2'), spin('q2', 's0'), spin('q3', 's1')],
    });
    for (final id in ['q1', 'q2', 'q3']) {
      await tester.tap(find.text('Faire tourner la roue'));
      await tester.pumpAndSettle();
      expect(find.text('Question $id ?'), findsOneWidget);
      await tester.tap(find.text('Réponse A $id'));
      await tester.pumpAndSettle();
    }
    expect(sent, [
      {
        'answers': [
          {'id': 'q1', 'choice_id': 'a'},
          {'id': 'q2', 'choice_id': 'a'},
          {'id': 'q3', 'choice_id': 'a'},
        ],
      },
    ]);
  });

  testWidgets('ouvrir la boîte : chaque boîte cache une question', (tester) async {
    Map<String, Object?> box(String id, int number) => {
      'id': id,
      'number': number,
      'prompt': 'Question $number ?',
      'choices': [
        {'id': 'a', 'text': 'Vrai'},
        {'id': 'b', 'text': 'Faux'},
      ],
    };
    await show(tester, 'BOX', {
      'boxes': [box('q1', 1), box('q2', 2)],
    });
    await tester.tap(find.bySemanticsLabel('Boîte 2'));
    await tester.pump();
    expect(find.text('Question 2 ?'), findsOneWidget);
    await tester.tap(find.text('Faux'));
    await tester.pump();
    expect(find.bySemanticsLabel('Boîte 2, déjà ouverte'), findsOneWidget);
    expect(sent, isEmpty);
    await tester.tap(find.bySemanticsLabel('Boîte 1'));
    await tester.pump();
    await tester.tap(find.text('Vrai'));
    await tester.pump();
    expect(sent, [
      {
        'answers': [
          {'id': 'q2', 'choice_id': 'b'},
          {'id': 'q1', 'choice_id': 'a'},
        ],
      },
    ]);
  });

  testWidgets('cartes aléatoires : tirer, retourner, dire si on savait', (tester) async {
    await show(tester, 'RANDOM_CARDS', {
      'cards': [
        {'id': 'c1', 'front': 'Clovis', 'back': 'Roi des Francs'},
        {'id': 'c2', 'front': '1789', 'back': 'La Révolution'},
      ],
    });
    for (final (front, back, knew) in [
      ('Clovis', 'Roi des Francs', true),
      ('1789', 'La Révolution', false),
    ]) {
      await tester.tap(find.text('Tirer une carte'));
      await tester.pump();
      expect(find.text(front), findsOneWidget);
      await tester.tap(find.text('Retourner la carte'));
      await tester.pump();
      expect(find.text(back), findsOneWidget);
      await tester.tap(find.text(knew ? 'Je savais' : 'Je ne savais pas'));
      await tester.pump();
    }
    expect(sent, [
      {
        'cards': [
          {'id': 'c1', 'knew': true},
          {'id': 'c2', 'knew': false},
        ],
      },
    ]);
  });

  testWidgets('vrai ou faux', (tester) async {
    await show(tester, 'TRUE_FALSE', {'statement': 'La Bastille est prise en 1789.'});
    await tester.tap(find.text('❌ Faux'));
    expect(sent, [
      {'value': false},
    ]);
  });

  testWidgets(
    'étape 25 : la consigne du serveur, au niveau de la classe, remplace la consigne par défaut',
    (tester) async {
      await show(tester, 'TRUE_FALSE', {'statement': 'La Bastille est prise en 1789.'});
      expect(find.text('Vrai ou faux ?'), findsOneWidget);
      await show(tester, 'TRUE_FALSE', {
        'statement': 'La Bastille est prise en 1789.',
      }, instruction: 'Lis la phrase. Est-ce vrai ou faux ?');
      expect(find.text('Lis la phrase. Est-ce vrai ou faux ?'), findsOneWidget);
      expect(find.text('Vrai ou faux ?'), findsNothing);
      await show(tester, 'FILL_BLANK', {
        'text': 'La ___ est prise en 1789.',
      }, instruction: 'Il manque un mot. Écris-le.');
      expect(find.text('Il manque un mot. Écris-le.'), findsOneWidget);

      Map<String, Object?> item([String? instruction]) => {
        'id': 'i1',
        'position': 1,
        'block': 'core',
        'type': 'TRUE_FALSE',
        'payload': <String, Object?>{},
        'instruction': ?instruction,
      };
      expect(SessionItem.fromJson(item('Lis la phrase.')).instruction, 'Lis la phrase.');
      expect(SessionItem.fromJson(item()).instruction, isNull); // serveur plus ancien
    },
  );

  testWidgets('texte à trou : la réponse s\'écrit dans la phrase', (tester) async {
    await show(tester, 'FILL_BLANK', {
      'text': 'La Révolution commence en ___.',
      'hint': 'Une année',
    });
    expect(find.textContaining('______'), findsOneWidget);
    expect(find.text('💡 Une année'), findsOneWidget);
    await tester.enterText(find.byType(TextField), ' 1789 ');
    await tester.pump();
    expect(find.textContaining(' 1789 '), findsWidgets);
    await tester.tap(find.text('Valider'));
    expect(sent, [
      {'text': '1789'},
    ]);
  });

  testWidgets('mot éclair : le mot se cache, puis on l\'écrit de mémoire', (tester) async {
    await show(tester, 'WORD_FLASH', {
      'prompt': 'Regarde bien le mot, puis écris-le sans le voir.',
      'word': 'hôpital',
      'show_ms': 3000,
      'sentence': 'Le docteur travaille à l\'___.',
    }, instruction: 'Regarde bien le mot. Il va se cacher. Écris-le.');
    expect(find.text('hôpital'), findsOneWidget);
    expect(find.byType(TextField), findsNothing);
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
    expect(find.text('hôpital'), findsNothing); // caché
    expect(find.text('💡 Le docteur travaille à l\'___.'), findsOneWidget);
    await tester.enterText(find.byType(TextField), ' hopital ');
    await tester.pump();
    await tester.tap(find.text('Valider'));
    expect(sent, [
      {'text': 'hopital'},
    ]);
  });

  testWidgets('mot éclair : « Je l\'ai retenu » cache le mot tout de suite', (tester) async {
    await show(tester, 'WORD_FLASH', {
      'prompt': 'Écris le mot.',
      'word': 'chevaux',
      'show_ms': 5000,
    });
    await tester.tap(find.text('Je l\'ai retenu'));
    await tester.pump();
    expect(find.text('chevaux'), findsNothing);
    expect(find.byType(TextField), findsOneWidget);
    await tester.pump(const Duration(seconds: 6)); // le minuteur annulé ne fait rien
  });

  testWidgets('lettres mélangées : toucher dans l\'ordre, retirer une lettre', (tester) async {
    await show(tester, 'SCRAMBLE', {
      'prompt': 'Remets les lettres dans l\'ordre pour écrire le mot.',
      'letters': [
        {'id': 'l2', 'text': 'u'},
        {'id': 'l3', 'text': 'n'},
        {'id': 'l1', 'text': 'l'},
        {'id': 'l4', 'text': 'e'},
      ],
    });
    expect(find.text('Encore 4 lettre(s)'), findsOneWidget);
    for (final letter in ['l', 'n']) {
      await tester.tap(find.text(letter));
      await tester.pump();
    }
    await tester.tap(find.text('n')); // placée par erreur : retirée
    await tester.pump();
    for (final letter in ['u', 'n', 'e']) {
      await tester.tap(find.text(letter));
      await tester.pump();
    }
    await tester.tap(find.text('Valider'));
    expect(sent, [
      {
        'order': ['l1', 'l2', 'l3', 'l4'],
      },
    ]);
  });

  testWidgets('dictée : le mot est lu à voix haute, jamais affiché', (tester) async {
    final speaker = FakeSpeaker();
    DictationView.speakerFactory = () => speaker;
    addTearDown(() => DictationView.speakerFactory = PhoneSpeaker.new);
    await show(tester, 'DICTATION', {
      'prompt': 'Écoute le mot, puis écris-le.',
      'word': 'hôpital',
      'sentence': 'Le docteur travaille à l\'___.',
      'spoken_sentence': 'Le docteur travaille à l\'hôpital.',
    });
    await tester.pump();
    expect(speaker.said, ['hôpital', 'Le docteur travaille à l\'hôpital.', 'hôpital']);
    expect(find.text('hôpital'), findsNothing);
    expect(find.text('💡 Le docteur travaille à l\'___.'), findsOneWidget);
    await tester.tap(find.text('Réécouter'));
    await tester.pump();
    expect(speaker.said, hasLength(6));
    await tester.enterText(find.byType(TextField), 'hôpital');
    await tester.pump();
    await tester.tap(find.text('Valider'));
    expect(sent, [
      {'text': 'hôpital'},
    ]);
  });

  testWidgets('dictée sans voix française : le mot s\'affiche trois secondes', (tester) async {
    DictationView.speakerFactory = () => FakeSpeaker(voice: false);
    addTearDown(() => DictationView.speakerFactory = PhoneSpeaker.new);
    await show(tester, 'DICTATION', {'prompt': 'Écoute.', 'word': 'chevaux'});
    await tester.pump();
    expect(find.text('chevaux'), findsOneWidget);
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
    expect(find.text('chevaux'), findsNothing);
    expect(find.textContaining('ne sait pas lire à voix haute'), findsOneWidget);
  });

  testWidgets('carte mémoire : retourner, puis dire si on savait', (tester) async {
    await show(tester, 'FLASHCARD', {'front': '1789', 'back': 'Début de la Révolution'});
    expect(find.text('Je savais 👍'), findsNothing);
    await tester.tap(find.text('Retourner la carte'));
    await tester.pumpAndSettle();
    expect(find.text('Début de la Révolution'), findsOneWidget);
    await tester.tap(find.text('Je ne savais pas'));
    expect(sent, [
      {'self_assessment': 'didnt_know'},
    ]);
  });

  testWidgets('association : relier, détacher, valider quand tout est relié', (tester) async {
    await show(tester, 'MATCH', {
      'left': [
        {'id': 'l1', 'text': '1789'},
        {'id': 'l2', 'text': 'Louis XVI'},
      ],
      'right': [
        {'id': 'r1', 'text': 'Roi de France'},
        {'id': 'r2', 'text': 'Révolution'},
      ],
    });
    expect(find.text('Encore 2 à relier'), findsOneWidget);
    await tester.tap(find.text('1789'));
    await tester.pump();
    await tester.tap(find.text('Roi de France')); // erreur…
    await tester.pump();
    await tester.tap(find.text('Roi de France')); // … détachée
    await tester.pump();
    expect(find.text('Encore 2 à relier'), findsOneWidget);
    await tester.tap(find.text('Révolution')); // la droite d'abord, puis la gauche
    await tester.pump();
    await tester.tap(find.text('1789'));
    await tester.pump();
    await tester.tap(find.text('Louis XVI'));
    await tester.pump();
    await tester.tap(find.text('Roi de France'));
    await tester.pump();
    await tester.tap(find.text('Valider'));
    expect(sent, [
      {
        'pairs': [
          ['l1', 'r2'],
          ['l2', 'r1'],
        ],
      },
    ]);
  });

  testWidgets('défi rapide : une affirmation à la fois, avec le temps passé', (tester) async {
    await show(tester, 'SPEED_CHALLENGE', {
      'time_limit_s': 30,
      'statements': [
        {'id': 's1', 'text': 'La Bastille est prise en 1789.'},
        {'id': 's2', 'text': 'Louis XVI est empereur.'},
      ],
    });
    expect(find.text('⏱️ 30 s'), findsOneWidget);
    await tester.pump(const Duration(milliseconds: 2000));
    expect(find.text('⏱️ 28 s'), findsOneWidget);
    await tester.tap(find.text('✅ Vrai'));
    await tester.pump();
    expect(find.text('Louis XVI est empereur.'), findsOneWidget);
    await tester.pump(const Duration(milliseconds: 1000));
    await tester.tap(find.text('❌ Faux'));
    await tester.pump();
    expect(sent.single['answers'], [
      {'id': 's1', 'value': true},
      {'id': 's2', 'value': false},
    ]);
    expect(sent.single['elapsed_ms'], 3000);
  });

  testWidgets('défi rapide : le temps écoulé envoie les réponses données', (tester) async {
    await show(tester, 'SPEED_CHALLENGE', {
      'time_limit_s': 5,
      'statements': [
        {'id': 's1', 'text': 'A'},
        {'id': 's2', 'text': 'B'},
      ],
    });
    await tester.tap(find.text('✅ Vrai'));
    await tester.pump(const Duration(seconds: 6));
    expect(sent.single['answers'], [
      {'id': 's1', 'value': true},
    ]);
    expect(sent.single['elapsed_ms'], 5000);
  });

  testWidgets('correction du défi rapide : élément par élément', (tester) async {
    const item = SessionItem(
      id: 'i1',
      position: 0,
      block: Block.speed,
      type: 'SPEED_CHALLENGE',
      difficulty: 1,
      payload: {
        'statements': [
          {'id': 's1', 'text': 'La Bastille est prise en 1789.'},
          {'id': 's2', 'text': 'Le roi fait construire la Bastille en 1789.'},
        ],
      },
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: CorrectionView(
              item: item,
              correction: const Correction(
                result: AttemptResult.partial,
                score: 0.5,
                correctAnswer: '1 bonne(s) réponse(s) sur 2',
                details: [
                  {'id': 's1', 'correct': true, 'expected': true},
                  {
                    'id': 's2',
                    'correct': false,
                    'expected': false,
                    'correction': 'Le peuple de Paris prend la Bastille.',
                  },
                ],
              ),
              onContinue: () {},
            ),
          ),
        ),
      ),
    );
    expect(find.text('👍 Presque !'), findsOneWidget);
    expect(find.text('La Bastille est prise en 1789. (vrai)'), findsOneWidget);
    expect(
      find.text(
        'Le roi fait construire la Bastille en 1789.\n'
        'C\'était faux. Le peuple de Paris prend la Bastille.',
      ),
      findsOneWidget,
    );
    expect(find.textContaining('La bonne réponse est'), findsNothing);
  });
}
