import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ludifun/app/theme.dart';
import 'package:ludifun/features/session/activities/activity_registry.dart';
import 'package:ludifun/features/session/activities/common.dart';
import 'package:ludifun/features/session/correction_view.dart';
import 'package:ludifun/models/session.dart';

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
  }

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
