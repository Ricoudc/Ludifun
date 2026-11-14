import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ludifun/app/theme.dart';
import 'package:ludifun/core/speech.dart';
import 'package:ludifun/features/session/activities/activity_registry.dart';
import 'package:ludifun/features/session/activities/common.dart';

class _Speaker implements Speaker {
  final said = <String>[];

  @override
  Future<bool> speak(String text, {String language = 'fr-FR'}) async {
    said.add(text);
    return true;
  }

  @override
  Future<void> stop() async {}
}

/// Jeux d'apprentissage de novembre 2026 (§5.98) : chaque écran envoie la réponse attendue.
void main() {
  late List<Map<String, Object?>> sent;
  setUp(() => sent = []);

  Future<void> show(WidgetTester tester, String type, Map<String, Object?> payload) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.5;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        theme: buildTheme(),
        home: Scaffold(
          body: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: activityRegistry[type]!(payload, sent.add),
          ),
        ),
      ),
    );
    await tester.pump();
  }

  Future<void> tap(WidgetTester tester, Finder finder) async {
    await tester.ensureVisible(finder);
    await tester.tap(finder);
    await tester.pump();
  }

  testWidgets('chasse à l\'erreur : toucher le mot faux, puis la correction', (tester) async {
    await show(tester, 'SPOT_ERROR', {
      'prompt': 'Une phrase de ta leçon contient une erreur.',
      'words': [
        {'id': 'w1', 'text': 'La'},
        {'id': 'w2', 'text': 'Révolution'},
        {'id': 'w3', 'text': 'commence'},
        {'id': 'w4', 'text': 'en'},
        {'id': 'w5', 'text': '1798.'},
      ],
      'choices': [
        {'id': 'c1', 'text': '1789'},
        {'id': 'c2', 'text': '1815'},
        {'id': 'c3', 'text': '1492'},
      ],
    });
    expect(find.text('Touche le mot qui est faux.'), findsOneWidget);
    await tap(tester, find.text('1798.'));
    expect(find.text('Par quoi remplacer « 1798. » ?'), findsOneWidget);
    await tap(tester, find.text('1789'));
    expect(sent, [
      {'word_id': 'w5', 'choice_id': 'c1'},
    ]);
  });

  testWidgets('phrase qui s\'efface : la phrase, puis les mots cachés à écrire', (tester) async {
    await show(tester, 'FADING', {
      'prompt': 'Lis bien la phrase.',
      'words': ['La', 'Révolution', 'commence', 'en', '1789.'],
      'hidden': [1, 4],
      'memorize_s': 5,
    });
    expect(find.text('La Révolution commence en 1789.'), findsOneWidget);
    await tester.pump(const Duration(seconds: 5));
    expect(find.text('La Révolution commence en 1789.'), findsNothing);
    expect(find.byType(TextField), findsNWidgets(2));
    await tester.enterText(find.byType(TextField).first, ' révolution ');
    await tester.enterText(find.byType(TextField).last, '1789');
    await tap(tester, find.text('Valider'));
    expect(sent, [
      {
        'answers': [
          [1, 'révolution'],
          [4, '1789'],
        ],
      },
    ]);
  });

  testWidgets('le bon ordre : ranger les étapes, écarter la fausse', (tester) async {
    await show(tester, 'STEP_ORDER', {
      'prompt': 'Remets les étapes dans l\'ordre.',
      'items': [
        {'id': 's2', 'text': 'Aligner les unités'},
        {'id': 's4', 'text': 'Commencer par la gauche'},
        {'id': 's1', 'text': 'Poser l\'opération'},
        {'id': 's3', 'text': 'Calculer colonne par colonne'},
      ],
    });
    await tap(tester, find.text('Poser l\'opération'));
    await tap(tester, find.text('Aligner les unités'));
    await tap(tester, find.text('Calculer colonne par colonne'));
    await tap(tester, find.text('Mettre une étape de côté'));
    await tap(tester, find.text('Commencer par la gauche'));
    await tap(tester, find.text('Valider'));
    expect(sent, [
      {
        'order': ['s1', 's2', 's3'],
        'intruder': 's4',
      },
    ]);
  });

  testWidgets('le correcteur : Ludi se trompe, et pourquoi', (tester) async {
    await show(tester, 'CHECK_LUDI', {
      'question': 'Combien font 7 × 8 ?',
      'ludi_answer': '54',
      'reasons': [
        {'id': 'r1', 'text': 'Une erreur de calcul'},
        {'id': 'r2', 'text': 'Il a mal lu la question'},
        {'id': 'r3', 'text': 'Il ne le savait pas'},
      ],
    });
    expect(find.text('🦉 Ludi a répondu : « 54 »'), findsOneWidget);
    await tap(tester, find.text('❌ Il se trompe'));
    await tap(tester, find.text('Une erreur de calcul'));
    expect(sent, [
      {'right': false, 'reason_id': 'r1'},
    ]);
  });

  testWidgets('qui suis-je : un indice de plus, puis la réponse', (tester) async {
    await show(tester, 'WHO_AM_I', {
      'prompt': 'Qui suis-je ?',
      'clues': ['Je suis en haut.', 'Je dis en combien de parts.', 'Je suis au-dessus du trait.'],
      'choices': [
        {'id': 'c1', 'text': 'Le dénominateur'},
        {'id': 'c2', 'text': 'Le numérateur'},
      ],
    });
    expect(find.text('Je dis en combien de parts.'), findsNothing);
    await tap(tester, find.text('Un autre indice'));
    expect(find.text('Je dis en combien de parts.'), findsOneWidget);
    await tap(tester, find.text('Le numérateur'));
    expect(sent, [
      {'choice_id': 'c2', 'clues_used': 2},
    ]);
  });

  testWidgets('l\'escalier : une marche après l\'autre', (tester) async {
    Map<String, Object?> step(String id, String prompt) => {
      'id': id,
      'prompt': prompt,
      'choices': [
        {'id': 'c1', 'text': 'Oui $id'},
        {'id': 'c2', 'text': 'Non $id'},
      ],
    };
    await show(tester, 'STAIRS', {
      'prompt': 'Monte l\'escalier.',
      'steps': [step('m1', 'Facile ?'), step('m2', 'Moyen ?'), step('m3', 'Difficile ?')],
    });
    expect(find.text('Marche 1 sur 3'), findsOneWidget);
    await tap(tester, find.text('Oui m1'));
    expect(find.text('Marche 2 sur 3'), findsOneWidget);
    await tap(tester, find.text('Non m2'));
    await tap(tester, find.text('Oui m3'));
    expect(sent, [
      {
        'answers': [
          ['m1', 'c1'],
          ['m2', 'c2'],
          ['m3', 'c1'],
        ],
      },
    ]);
  });

  testWidgets('le train des mots : écouter, accrocher les wagons', (tester) async {
    final speaker = _Speaker();
    ListenButton.speakerFactory = () => speaker;
    addTearDown(() => ListenButton.speakerFactory = PhoneSpeaker.new);
    await show(tester, 'WORD_TRAIN', {
      'prompt': 'Écoute le mot.',
      'say': 'vélo',
      'lang': 'fr-FR',
      'length': 2,
      'wagons': [
        {'id': 'v3', 'text': 'pa'},
        {'id': 'v2', 'text': 'lo'},
        {'id': 'v1', 'text': 'vé'},
        {'id': 'v4', 'text': 'mo'},
      ],
    });
    expect(find.text('vélo'), findsNothing); // le mot n'est pas écrit : il s'écoute
    await tap(tester, find.byType(ListenButton));
    await tester.pumpAndSettle();
    expect(speaker.said.single, contains('vélo'));
    await tap(tester, find.text('vé'));
    await tap(tester, find.text('lo'));
    await tap(tester, find.text('Le train part !'));
    expect(sent, [
      {
        'order': ['v1', 'v2'],
      },
    ]);
  });

  testWidgets('compte et touche : toucher autant d\'objets', (tester) async {
    await show(tester, 'COUNT_TOUCH', {
      'prompt': 'Touche 3 objets.',
      'say': '3',
      'target': 3,
      'emoji': '🍎',
      'objects': ['o1', 'o2', 'o3', 'o4', 'o5'],
    });
    for (final id in ['o1', 'o2', 'o4', 'o2', 'o5']) {
      await tap(tester, find.byKey(ValueKey(id)));
    }
    expect(find.text('Touchés : 3'), findsOneWidget);
    await tap(tester, find.text('J\'ai fini'));
    expect(sent.single['selected'], unorderedEquals(['o1', 'o4', 'o5']));
  });
}
