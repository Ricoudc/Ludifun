import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../support/screenshots.dart';

import 'package:ludifun/features/session/activities/activity_registry.dart';
import 'package:ludifun/features/session/activities/memory_view.dart';
import 'package:ludifun/models/account.dart';

/// Étape 21 : les jeux graphiques, du geste de l'enfant à la réponse envoyée au serveur.
void main() {
  Future<List<Json>> show(WidgetTester tester, String type, Json payload) async {
    final sent = <Json>[];
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: activityRegistry[type]!(payload, sent.add),
          ),
        ),
      ),
    );
    await shot(tester, 'a_$type');
    return sent;
  }

  Future<void> tap(WidgetTester tester, String text) async {
    await tester.ensureVisible(find.text(text).last);
    await tester.tap(find.text(text).last);
    await tester.pump();
  }

  const steps = {
    'prompt': 'Les étapes de la digestion',
    'items': [
      {'id': 'i1', 'text': 'Estomac'},
      {'id': 'i2', 'text': 'Bouche'},
      {'id': 'i3', 'text': 'Intestin'},
    ],
  };

  testWidgets('remettre dans l\'ordre : toucher dans l\'ordre, retirer, valider', (tester) async {
    final sent = await show(tester, 'ORDER', steps);
    expect(find.text('Remets dans l\'ordre'), findsOneWidget);
    expect(find.text('Encore 3 à placer'), findsOneWidget);

    await tap(tester, 'Estomac');
    await tap(tester, 'Estomac'); // retirée
    await tap(tester, 'Bouche');
    await tap(tester, 'Estomac');
    await tap(tester, 'Intestin');
    await tap(tester, 'Valider');
    expect(sent, [
      {
        'order': ['i2', 'i1', 'i3'],
      },
    ]);
  });

  testWidgets('frise chronologique : même geste, autre consigne', (tester) async {
    final sent = await show(tester, 'TIMELINE', {
      'prompt': 'Place les événements sur la frise',
      'items': [
        {'id': 'i1', 'text': 'Prise de la Bastille'},
        {'id': 'i2', 'text': 'Sacre de Napoléon'},
        {'id': 'i3', 'text': 'Déclaration des droits de l\'homme'},
      ],
    });
    expect(find.text('Frise chronologique'), findsOneWidget);
    for (final text in [
      'Prise de la Bastille',
      'Déclaration des droits de l\'homme',
      'Sacre de Napoléon',
    ]) {
      await tap(tester, text);
    }
    await tap(tester, 'Valider');
    expect(sent.single['order'], ['i1', 'i3', 'i2']);
  });

  testWidgets('ranger dans les cases : étiquette puis case ; ressortir une étiquette', (
    tester,
  ) async {
    final sent = await show(tester, 'CLASSIFY', {
      'prompt': 'Vertébrés ou invertébrés ?',
      'categories': [
        {'id': 'c1', 'name': 'Vertébrés'},
        {'id': 'c2', 'name': 'Invertébrés'},
      ],
      'items': [
        {'id': 'i1', 'text': 'Chat'},
        {'id': 'i2', 'text': 'Escargot'},
      ],
    });
    expect(find.text('Encore 2 à ranger'), findsOneWidget);

    await tap(tester, 'Chat');
    await tap(tester, 'Invertébrés');
    await tap(tester, 'Chat'); // ressortie de la mauvaise case
    await tap(tester, 'Chat');
    await tap(tester, 'Vertébrés');
    await tap(tester, 'Escargot');
    await tap(tester, 'Invertébrés');
    await tap(tester, 'Valider');
    expect(sent.single['assignments'], [
      ['i1', 'c1'],
      ['i2', 'c2'],
    ]);
  });

  testWidgets('memory : les cartes se referment, les paires restent, envoi à la dernière paire', (
    tester,
  ) async {
    final sent = await show(tester, 'MEMORY', {
      'prompt': 'Retrouve les paires qui vont ensemble.',
      'cards': [
        {'id': 'c1', 'text': 'Louis XVI', 'pair': 'p1'},
        {'id': 'c2', 'text': '1789', 'pair': 'p2'},
        {'id': 'c3', 'text': 'Roi de France', 'pair': 'p1'},
        {'id': 'c4', 'text': 'Révolution', 'pair': 'p2'},
      ],
    });
    final hidden = find.bySemanticsLabel('Carte cachée');
    expect(hidden, findsNWidgets(4));

    Future<void> flip(int index) async {
      await tester.tap(find.bySemanticsLabel('Carte cachée').at(index));
      await tester.pump();
    }

    await flip(0); // Louis XVI
    await flip(0); // 1789 : pas la même paire
    expect(find.text('1789'), findsOneWidget);
    await tester.pump(MemoryView.flipBack);
    expect(hidden, findsNWidgets(4)); // refermées

    await flip(0); // Louis XVI
    await flip(1); // Roi de France
    expect(find.text('Louis XVI'), findsOneWidget);
    await tester.pump(MemoryView.flipBack);
    expect(hidden, findsNWidgets(2)); // la paire reste visible
    expect(find.textContaining('1 paire(s) trouvée(s) sur 2 · 2 coup(s)'), findsOneWidget);

    await flip(0);
    await flip(0);
    expect(sent, [
      {
        'moves': [
          ['c1', 'c2'],
          ['c1', 'c3'],
          ['c2', 'c4'],
        ],
      },
    ]);
  });

  testWidgets('memory : une troisième carte referme tout de suite les deux précédentes', (
    tester,
  ) async {
    await show(tester, 'MEMORY', {
      'prompt': 'Retrouve les paires qui vont ensemble.',
      'cards': [
        {'id': 'c1', 'text': 'A', 'pair': 'p1'},
        {'id': 'c2', 'text': 'B', 'pair': 'p2'},
        {'id': 'c3', 'text': 'C', 'pair': 'p3'},
        {'id': 'c4', 'text': 'a', 'pair': 'p1'},
        {'id': 'c5', 'text': 'b', 'pair': 'p2'},
        {'id': 'c6', 'text': 'c', 'pair': 'p3'},
      ],
    });
    await tester.tap(find.bySemanticsLabel('Carte cachée').at(0));
    await tester.pump();
    await tester.tap(find.bySemanticsLabel('Carte cachée').at(0));
    await tester.pump();
    await tester.tap(find.bySemanticsLabel('Carte cachée').at(0)); // C, sans attendre
    await tester.pump();
    expect(find.text('A'), findsNothing);
    expect(find.text('B'), findsNothing);
    expect(find.text('C'), findsOneWidget);
    await tester.pump(MemoryView.flipBack);
  });
}
