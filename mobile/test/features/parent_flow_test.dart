import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ludifun/app/app.dart';
import 'package:ludifun/app/router.dart';
import 'package:ludifun/core/storage/credentials.dart';
import 'package:ludifun/features/capture/capture_controller.dart';
import 'package:ludifun/features/home/home_providers.dart';
import 'package:ludifun/features/parent/child_mistakes_screen.dart';
import 'package:ludifun/features/parent/file_sharer.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../support/fake_server.dart';
import '../support/fakes.dart';

const parent = ParentCredentials(accessToken: 'a1', refreshToken: 'r1', email: 'parent@example.fr');
final now = DateTime.utc(2026, 9, 23, 17);

Map<String, Object?> child({int devices = 0, String name = 'Emma', String grade = 'CM1'}) => {
  'id': 'c1',
  'display_name': name,
  'grade': grade,
  'avatar': '🦊',
  'created_at': '2026-09-01T10:00:00Z',
  'devices': devices,
};

Map<String, Object?> week(String monday, int sessions, int minutes, double? average) => {
  'week_start': monday,
  'sessions': sessions,
  'minutes': minutes,
  'average_score': average,
};

/// Une semaine de révisions d'Emma, telle que la calcule l'API (étape 8).
final dashboard = {
  'child_id': 'c1',
  'timezone': 'Europe/Paris',
  'this_week': week('2026-09-21', 4, 37, 8.5),
  'lessons_added_this_week': 2,
  'activities_this_week': {'MCQ': 4, 'FLASHCARD': 2, 'FILL_BLANK': 6},
  'subjects': [
    {'subject': 'french', 'mastery': 86, 'color': 'green', 'notions': 6},
    {'subject': 'math', 'mastery': 72, 'color': 'orange', 'notions': 5},
    {'subject': 'history', 'mastery': 91, 'color': 'green', 'notions': 8},
  ],
  'to_strengthen': [
    {
      'knowledge_id': 'k1',
      'label': 'Comparaison des fractions',
      'lesson_id': 'l2',
      'lesson_title': 'Les fractions',
      'subject': 'math',
      'mastery': 40,
      'status': 'not_mastered',
      'next_review_at': '2026-09-24T08:00:00Z',
      'level': 2,
      'explanation': 'Des réussites, mais encore fragile.',
    },
    {
      'knowledge_id': 'k2',
      'label': 'Imparfait',
      'lesson_id': 'l3',
      'lesson_title': 'Le passé',
      'subject': 'french',
      'mastery': 100,
      'status': 'to_review',
      'next_review_at': '2026-09-25T08:00:00Z',
      'level': 3,
      'explanation': 'Reconnaît la bonne réponse, pas encore la retrouver seul.',
    },
  ],
  'reviews_due': 3,
  'error_types': [
    {'error_type': 'confusion', 'label': 'Confond avec une autre notion', 'count': 7},
    {'error_type': 'random', 'label': 'Répond trop vite, au hasard', 'count': 2},
  ],
  'recurring_errors': [
    {
      'knowledge_id': 'k2',
      'label': 'Numérateur',
      'lesson_title': 'Les fractions',
      'error_type': 'confusion',
      'error_label': 'Confond avec une autre notion',
      'sessions': 3,
      'last_at': '2026-09-23T15:00:00Z',
    },
  ],
  'weeks': [
    week('2026-08-31', 1, 8, 5.5),
    week('2026-09-07', 2, 15, 6.5),
    week('2026-09-14', 3, 24, 7.5),
    week('2026-09-21', 4, 37, 8.5),
  ],
  'trend': 'up',
};

Map<String, Object?> session(String id, String title, String startedAt, double score) => {
  'session_id': id,
  'lesson_id': 'l1',
  'lesson_title': title,
  'subject': 'history',
  'kind': 'first',
  'status': 'completed',
  'started_at': startedAt,
  'completed_at': startedAt,
  'minutes': 9,
  'score_on_10': score,
  'notions': [
    {'label': '1789', 'status': 'mastered'},
    {'label': 'États généraux', 'status': 'to_review'},
  ],
};

/// Feuille de partage simulée : garde les fichiers remis au parent.
class FakeSharer implements FileSharer {
  final shared = <({String filename, Uint8List bytes, String mimeType, String? subject})>[];

  @override
  Future<void> share({
    required String filename,
    required Uint8List bytes,
    required String mimeType,
    String? subject,
  }) async => shared.add((filename: filename, bytes: bytes, mimeType: mimeType, subject: subject));
}

void main() {
  late FakeServer server;
  late FakeSharer sharer;
  late Map<String, Object?> emmaChild;

  setUp(() {
    sharer = FakeSharer();
    emmaChild = child();
    server = FakeServer()
      ..on('GET /v1/children', (_) => (200, [emmaChild]))
      ..on('GET /v1/children/c1/dashboard', (r) {
        expect(r.queryParameters['weeks'], 4);
        return (200, dashboard);
      });
  });

  Future<ProviderContainer> launch(WidgetTester tester, [Credentials credentials = parent]) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.5;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...overridesFor(server, MemoryCredentialStore(credentials)),
          nowProvider.overrideWithValue(() => now),
          imagePickerProvider.overrideWithValue(FakeImagePicker(gallery: 1)),
          imageCompressorProvider.overrideWithValue(FakeCompressor()),
          fileSharerProvider.overrideWithValue(sharer),
        ],
        retry: noRetry,
        child: const LudifunApp(),
      ),
    );
    await tester.pumpAndSettle();
    return ProviderScope.containerOf(tester.element(find.byType(LudifunApp)));
  }

  Future<void> go(WidgetTester tester, ProviderContainer container, String location) async {
    container.read(routerProvider).go(location);
    await tester.pumpAndSettle();
  }

  Future<void> tap(WidgetTester tester, Finder finder) async {
    await tester.ensureVisible(finder);
    await tester.tap(finder);
    await tester.pumpAndSettle();
  }

  testWidgets('critère de l\'étape 12 : le parent suit une semaine de révisions d\'Emma', (
    tester,
  ) async {
    await launch(tester);
    expect(find.text('Emma · CM1'), findsOneWidget);
    await tap(tester, find.text('Emma · CM1'));

    // Cette semaine.
    expect(find.text('🦊 Emma · CM1'), findsOneWidget);
    expect(find.text('4'), findsOneWidget);
    expect(find.text('37'), findsOneWidget);
    expect(find.text('8,5 / 10'), findsOneWidget);
    expect(find.text('🔄 3 notions à revoir aujourd\'hui'), findsOneWidget);

    // Réussite par matière, dans l'ordre du programme, avec le pourcentage écrit.
    expect(find.text('📖 Français'), findsOneWidget);
    expect(find.text('86 %'), findsOneWidget);
    expect(find.text('72 %'), findsOneWidget);
    expect(find.text('91 %'), findsOneWidget);

    // À renforcer, progression, activités.
    expect(find.text('Comparaison des fractions'), findsOneWidget);
    expect(find.text('Des réussites, mais encore fragile. · Les fractions'), findsOneWidget);
    expect(find.text('Imparfait'), findsOneWidget);
    // Réussie à 100 % en QCM, mais pas encore retrouvée seule : le niveau, pas le pourcentage.
    expect(
      find.text('Reconnaît la bonne réponse, pas encore la retrouver seul. · Le passé'),
      findsOneWidget,
    );
    expect(find.text('100 %'), findsNothing);
    expect(find.bySemanticsLabel('Niveau 3 sur 5 : En cours d\'acquisition'), findsOneWidget);

    // Erreurs fréquentes : l'erreur récurrente, puis les types d'erreurs du mois.
    expect(find.text('Erreurs fréquentes'), findsOneWidget);
    expect(find.text('Numérateur : confond avec une autre notion'), findsOneWidget);
    expect(find.text('Les fractions · dans 3 séances'), findsOneWidget);
    expect(find.text('Confond avec une autre notion · 7'), findsOneWidget);
    expect(find.text('Répond trop vite, au hasard · 2'), findsOneWidget);
    expect(find.text('Note moyenne par semaine · en progression ↗'), findsOneWidget);
    expect(
      find.bySemanticsLabel('Semaine du 21/9 : 4 séances, 37 min, 8,5 / 10 en moyenne'),
      findsOneWidget,
    );
    expect(find.text('🎮 Quiz 4'), findsOneWidget);
    expect(find.text('✍️ Textes à trous 6'), findsOneWidget);
    expect(find.text('🃏 Cartes 2'), findsOneWidget);

    // Définitions affichables telles quelles.
    await tap(tester, find.byTooltip('Comment lire ce tableau'));
    expect(find.textContaining('Réussite par matière : maîtrise actuelle'), findsOneWidget);
    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();

    // Écran P4 : historique paginé.
    server
      ..on('GET /v1/children/c1/history', (r) {
        final older = r.queryParameters['before'] != null;
        return (
          200,
          older
              ? {
                  'sessions': [session('s1', 'Les fractions', '2026-09-20T15:00:00Z', 6)],
                  'next_before': null,
                }
              : {
                  'sessions': [
                    session('s3', 'La Révolution française', '2026-09-23T15:05:00Z', 8.5),
                    session('s2', 'La Révolution française', '2026-09-22T16:00:00Z', 7),
                  ],
                  'next_before': '2026-09-22T16:00:00Z',
                },
        );
      })
      ..on(
        'GET /v1/children/c1/devices',
        (_) => (
          200,
          [
            {
              'id': 'd1',
              'name': 'Appareil Android',
              'created_at': '2026-09-01T10:00:00Z',
              'last_seen_at': '2026-09-23T15:05:00Z',
            },
          ],
        ),
      );
    await tap(tester, find.byTooltip('Historique et réglages'));
    expect(find.text('8,5 / 10'), findsOneWidget);
    expect(find.textContaining('aujourd\'hui à'), findsWidgets);
    expect(find.text('✓ 1789'), findsNWidgets(2));
    expect(find.text('⚠ États généraux'), findsNWidgets(2));
    await tap(tester, find.text('Voir les séances plus anciennes'));
    expect(find.text('📐 Les fractions'), findsNothing); // matière de la fausse séance : histoire
    expect(find.textContaining('Les fractions'), findsOneWidget);
    expect(find.text('Voir les séances plus anciennes'), findsNothing);

    // « Pourquoi ces activités ? » : la raison de chaque choix du moteur (§126).
    server.on(
      'GET /v1/children/c1/sessions/s3',
      (_) => (
        200,
        {
          'session_id': 's3',
          'kind': 'review',
          'started_at': '2026-09-23T15:05:00Z',
          'engine_version': '1.0.0',
          'activities': [
            {
              'position': 1,
              'block': 'warmup',
              'activity': 'QCM',
              'difficulty': 2,
              'notions': ['États généraux'],
              'result': 'incorrect',
              'help_level': 0,
              'reason': 'Révision prévue aujourd\'hui (score 40) : difficulté 1.',
            },
            {
              'position': 2,
              'block': 'remediation',
              'activity': 'Vrai ou faux',
              'difficulty': 1,
              'notions': ['États généraux'],
              'result': 'correct',
              'help_level': 2,
              'reason':
                  '2 échecs sur cette notion dans la séance : rappel puis activité plus facile.',
            },
          ],
          'decisions': [
            {
              'rule': 'remediation',
              'text':
                  '2 échecs sur cette notion dans la séance : rappel puis activité plus facile.',
              'position': 1,
            },
          ],
        },
      ),
    );
    await tap(tester, find.text('8,5 / 10'));
    expect(find.text('Pourquoi ces activités ?'), findsOneWidget);
    expect(find.text('Règles du moteur, version 1.0.0.'), findsOneWidget);
    expect(find.text('1. QCM · États généraux'), findsOneWidget);
    expect(find.text('Révision prévue aujourd\'hui (score 40) : difficulté 1.'), findsOneWidget);
    expect(find.text('✓ avec aide'), findsOneWidget);
    expect(
      find.text('• 2 échecs sur cette notion dans la séance : rappel puis activité plus facile.'),
      findsOneWidget,
    );
    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();

    // Appareil lié : délier après confirmation.
    expect(find.text('Appareil Android'), findsOneWidget);
    server.on('DELETE /v1/children/c1/devices/d1', (_) => (204, null));
    await tap(tester, find.text('Délier'));
    await tap(tester, find.widgetWithText(FilledButton, 'Délier'));
    expect(server.routes, contains('DELETE /v1/children/c1/devices/d1'));
  });

  testWidgets('ajouter un enfant (consentement), puis lier sa tablette par code ou QR', (
    tester,
  ) async {
    var linkedDevices = 0;
    server
      ..on('GET /v1/children', (_) => (200, <Object>[]))
      ..on('POST /v1/children', (r) {
        expect(r.data, {
          'display_name': 'Hugo',
          'grade': 'CE1',
          'avatar': '🐼',
          'parental_consent': true,
        });
        return (201, child(name: 'Hugo', grade: 'CE1'));
      })
      ..on(
        'POST /v1/children/c1/link-codes',
        (_) => (
          201,
          {
            'code': '482731',
            'qr': 'ludifun://lier/jeton-secret-128-bits',
            'expires_at': now.add(const Duration(minutes: 10)).toIso8601String(),
          },
        ),
      )
      ..on(
        'GET /v1/children/c1/devices',
        (_) => (
          200,
          [
            for (var i = 0; i < linkedDevices; i++)
              {
                'id': 'd$i',
                'name': null,
                'created_at': '2026-09-23T17:00:00Z',
                'last_seen_at': null,
              },
          ],
        ),
      );
    await launch(tester);
    await tap(tester, find.text('Ajouter un enfant'));

    await tester.enterText(find.byType(TextFormField), 'Hugo');
    await tap(tester, find.text('CE1'));
    await tap(tester, find.text('🐼'));
    await tap(tester, find.text('Créer le profil'));
    expect(
      find.text('Le consentement parental est nécessaire pour créer le profil.'),
      findsOneWidget,
    );
    expect(server.routes, isNot(contains('POST /v1/children')));
    await tap(tester, find.byType(CheckboxListTile));
    server.on('GET /v1/children', (_) => (200, [child(name: 'Hugo', grade: 'CE1')]));
    await tap(tester, find.text('Créer le profil'));

    // Code et QR code, avec le temps restant.
    expect(find.text('482 731'), findsOneWidget);
    expect(find.byType(QrImageView), findsOneWidget);
    final qr = tester.widget<QrImageView>(find.byType(QrImageView));
    expect(qr.semanticsLabel, 'QR code de liaison');
    expect(find.text('Valable encore 10 min 00 s · une seule utilisation'), findsOneWidget);
    expect(find.textContaining('Hugo'), findsWidgets);

    // La tablette saisit le code : l'écran le voit.
    linkedDevices = 1;
    await tester.pump(const Duration(seconds: 4));
    await tester.pumpAndSettle();
    expect(find.text('L\'appareil de Hugo est lié !'), findsOneWidget);
  });

  testWidgets('le parent photographie une leçon pour Emma', (tester) async {
    var polls = 0;
    server
      ..on(
        'GET /v1/children/c1/lessons/l9/content',
        (_) => (
          200,
          {
            'lesson_id': 'l9',
            'title': 'La Révolution française',
            'grade': 'CM1',
            'text': 'En 1789, les Français prennent la Bastille.',
            'notions': <Object>[],
          },
        ),
      )
      ..on('POST /v1/lessons', (r) {
        expect(r.queryParameters['child_id'], 'c1');
        return (202, {'id': 'l9', 'status': 'uploaded'});
      })
      ..on('GET /v1/lessons/l9', (r) {
        expect(r.queryParameters['child_id'], 'c1');
        return (
          200,
          {
            'id': 'l9',
            'status': polls++ < 1 ? 'reading' : 'ready',
            'failure_reason': null,
            'subject': 'history',
            'title': 'La Révolution française',
            'created_at': '2026-09-23T15:00:00Z',
            'steps': {'reading': 'done', 'analyzing': 'done', 'generating': 'done'},
            'knowledge': <Object>[],
            'can_retry': false,
          },
        );
      });
    final container = await launch(tester);
    await go(tester, container, Routes.childDashboard('c1'));
    await tap(tester, find.text('Ajouter une leçon pour Emma'));
    expect(find.text('📷 Photographier la leçon'), findsOneWidget);
    await tap(tester, find.text('Ajouter depuis la galerie'));
    await tester.tap(find.text('Analyser ma leçon'));
    for (var i = 0; i < 60 && find.textContaining('Voici tout').evaluate().isEmpty; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    await tester.pumpAndSettle();
    // Prête : le parent arrive sur ce que l'enfant verra, pour le vérifier.
    expect(find.text('Leçon prête : vérifiez les questions et les réponses.'), findsOneWidget);
    expect(find.text('La leçon, telle que l\'IA l\'a lue'), findsOneWidget);
  });

  testWidgets('tableau de bord : les leçons, prêtes ou en préparation', (tester) async {
    Map<String, Object?> lesson(String id, String status, String? title) => {
      'id': id,
      'status': status,
      'failure_reason': null,
      'subject': 'history',
      'title': title,
      'created_at': '2026-09-23T15:00:00Z',
    };
    server
      ..on('GET /v1/lessons', (r) {
        expect(r.queryParameters['child_id'], 'c1');
        return (200, [lesson('l9', 'generating', null), lesson('l2', 'ready', 'Les fractions')]);
      })
      ..on(
        'GET /v1/children/c1/lessons/l2/content',
        (_) => (
          200,
          {'lesson_id': 'l2', 'title': 'Les fractions', 'grade': 'CM1', 'notions': <Object>[]},
        ),
      );
    final container = await launch(tester);
    await go(tester, container, Routes.childDashboard('c1'));
    expect(find.text('Leçons'), findsOneWidget);
    expect(find.text('⏳ L\'IA la prépare… · touchez pour suivre'), findsOneWidget);
    expect(find.text('Leçon du mercredi 23 septembre'), findsOneWidget);
    await tap(tester, find.text('Les fractions'));
    expect(find.textContaining('Voici tout ce que l\'enfant verra'), findsOneWidget);
  });

  testWidgets('mot de passe oublié, puis lien de l\'e-mail', (tester) async {
    server
      ..on('POST /v1/auth/password-reset', (r) {
        expect(r.data, {'email': 'parent@example.fr'});
        return (202, {'status': 'ok'});
      })
      ..on('POST /v1/auth/password-reset/confirm', (r) {
        expect(r.data, {'token': 'ldf_r_abc', 'new_password': 'un nouveau mot de passe'});
        return (204, null);
      });
    final container = await launch(tester, const NoCredentials());
    await tap(tester, find.text('Je suis un parent'));
    await tap(tester, find.text('Mot de passe oublié ?'));
    await tester.enterText(find.byType(TextFormField), 'parent@example.fr');
    await tap(tester, find.text('Recevoir le lien'));
    expect(find.textContaining('un lien vient d\'être envoyé'), findsOneWidget);

    // Le lien ludifun://app/parent/nouveau-mot-de-passe?jeton=… ouvre cet écran.
    await go(tester, container, '/parent/nouveau-mot-de-passe?jeton=ldf_r_abc');
    await tester.enterText(find.byType(TextFormField), 'court');
    await tap(tester, find.text('Changer mon mot de passe'));
    expect(find.text('Au moins 12 caractères.'), findsOneWidget);
    await tester.enterText(find.byType(TextFormField), 'un nouveau mot de passe');
    await tap(tester, find.text('Changer mon mot de passe'));
    expect(find.text('Votre mot de passe est changé. Vous pouvez vous connecter.'), findsOneWidget);
  });

  testWidgets('modifier le profil, supprimer l\'enfant, supprimer le compte', (tester) async {
    server
      ..on(
        'GET /v1/children/c1/history',
        (_) => (200, {'sessions': <Object>[], 'next_before': null}),
      )
      ..on('GET /v1/children/c1/devices', (_) => (200, <Object>[]))
      ..on('PATCH /v1/children/c1', (r) {
        expect(r.data, {'display_name': 'Emma', 'grade': 'CM2', 'avatar': '🦊'});
        emmaChild = child(grade: 'CM2');
        return (200, emmaChild);
      })
      ..on('DELETE /v1/children/c1', (_) => (204, null))
      ..on('DELETE /v1/parent', (_) => (204, null));
    final container = await launch(tester);
    await go(tester, container, Routes.childSettings('c1'));
    expect(find.text('Emma n\'a pas encore fait de séance.'), findsOneWidget);

    await tap(tester, find.text('Modifier le profil'));
    await tap(tester, find.text('CM2'));
    await tap(tester, find.text('Enregistrer'));
    expect(server.routes, contains('PATCH /v1/children/c1'));

    await tap(tester, find.text('Supprimer Emma et toutes ses données'));
    expect(find.text('Supprimer le profil de Emma ?'), findsOneWidget);
    await tap(tester, find.widgetWithText(FilledButton, 'Supprimer'));
    expect(server.routes, contains('DELETE /v1/children/c1'));
    expect(find.text('Mes enfants'), findsOneWidget);

    await tap(tester, find.byTooltip('Mon compte'));
    await tap(tester, find.text('Supprimer mon compte'));
    await tap(tester, find.widgetWithText(FilledButton, 'Supprimer définitivement'));
    expect(server.routes, contains('DELETE /v1/parent'));
    expect(find.text('Qui utilise cet appareil ?'), findsOneWidget);
  });

  testWidgets('confirmer son adresse e-mail : bandeau, renvoi du lien, lien ouvert', (
    tester,
  ) async {
    var verified = false;
    Object? verification;
    server
      ..on(
        'GET /v1/parent',
        (_) => (200, {'id': 'p1', 'email': 'parent@example.fr', 'email_verified': verified}),
      )
      ..on('POST /v1/parent/verify-email', (_) => (202, {'status': 'ok'}))
      ..on('POST /v1/auth/verify-email', (r) {
        verification = r.data;
        verified = true;
        return (200, {'id': 'p1', 'email': 'parent@example.fr', 'email_verified': true});
      });
    final container = await launch(tester);
    expect(find.text('📧 Confirmez votre adresse'), findsOneWidget);
    expect(find.textContaining('Ouvrez le lien envoyé à parent@example.fr'), findsOneWidget);

    await tap(tester, find.text('Renvoyer le lien'));
    expect(server.routes, contains('POST /v1/parent/verify-email'));
    expect(find.text('Lien envoyé : regardez votre boîte e-mail.'), findsOneWidget);

    // Le lien de l'e-mail ouvre l'application.
    await go(tester, container, '${Routes.verifyEmail}?jeton=ldf_v_abc');
    expect(verification, {'token': 'ldf_v_abc'});
    expect(find.text('Adresse confirmée, merci !'), findsOneWidget);
    await tap(tester, find.text('Continuer'));
    expect(find.text('Mes enfants'), findsOneWidget);
    expect(find.text('📧 Confirmez votre adresse'), findsNothing);
  });

  testWidgets('choisir l\'IA de la famille : Ollama conseillé, test, modèle, clé', (tester) async {
    Map<String, Object?> provider(
      String code,
      String label, {
      bool key = false,
      bool url = false,
      bool recommended = false,
      String? model,
    }) => {
      'code': code,
      'label': label,
      'note': code == 'ollama' ? 'Gratuite, rien ne sort de la maison.' : '',
      'needs_key': key,
      'custom_url': url,
      'default_url': code == 'ollama' ? 'http://localhost:11434' : null,
      'default_model': model,
      'key_url': key ? 'https://console.anthropic.com' : '',
      'recommended': recommended,
      'available': true,
    };
    Object? family;
    var fallback = false;
    final configs = <String, Map<String, Object?>>{};
    Map<String, Object?> settings() => {
      'family': family,
      'fallback': fallback,
      'saved': configs.values.toList(),
      'server_provider': 'fake',
      'providers': [
        provider(
          'ollama',
          'Ollama (sur ce PC)',
          url: true,
          recommended: true,
          model: 'qwen2.5vl:7b',
        ),
        provider('claude', 'Claude (Anthropic)', key: true, model: 'claude-opus-5'),
        provider('fake', 'Démonstration (sans IA)'),
      ],
    };
    final saved = <Object?>[];
    final checked = <Object?>[];
    server
      ..on('GET /v1/parent/ai', (_) => (200, settings()))
      ..on('POST /v1/parent/ai/test', (r) {
        checked.add(r.data);
        return (
          200,
          {
            'ok': true,
            'message': 'Ollama répond, « qwen2.5vl:7b » est installé.',
            'models': ['llama3:8b', 'qwen2.5vl:7b'],
          },
        );
      })
      ..on('PUT /v1/parent/ai', (r) {
        saved.add(r.data);
        final body = r.data as Map<String, dynamic>;
        final code = body['provider'] as String;
        final key = body['api_key'] as String?;
        fallback = body['fallback'] as bool? ?? fallback;
        final previousHint = configs[code]?['key_hint'];
        family = configs[code] = {
          'provider': code,
          'model': body['model'],
          'base_url': body['base_url'],
          'key_hint': key == null ? previousHint : '…${key.substring(key.length - 4)}',
        };
        return (200, settings());
      })
      ..on('DELETE /v1/parent/ai/providers/claude', (_) {
        configs.remove('claude');
        family = null;
        return (204, null);
      });
    await launch(tester);
    await tap(tester, find.byTooltip('Mon compte'));
    await tap(tester, find.text('Intelligence artificielle'));
    expect(
      find.text('IA utilisée en ce moment : Démonstration (sans IA) (réglage du serveur)'),
      findsOneWidget,
    );
    // Ollama est proposé d'abord, déjà choisi, avec son adresse, et vérifié tout de suite.
    expect(find.text('Ollama (sur ce PC) · conseillé'), findsOneWidget);
    expect(find.text('Gratuite, rien ne sort de la maison.'), findsOneWidget);
    expect(find.widgetWithText(TextField, 'http://localhost:11434'), findsOneWidget);
    expect(find.text('Vide : qwen2.5vl:7b (conseillé)'), findsOneWidget);
    expect(checked, [
      {'provider': 'ollama', 'base_url': 'http://localhost:11434'},
    ]);
    expect(find.text('✅ Ollama répond, « qwen2.5vl:7b » est installé.'), findsOneWidget);
    // Serveur sans moteur de recherche : l'interrupteur dit comment l'installer (étape 24).
    expect(find.textContaining('Activer-Recherche-Ludifun.bat'), findsOneWidget);

    // Choisir un autre modèle le vérifie aussitôt ; l'enregistrement n'en refait pas un.
    await tap(tester, find.widgetWithText(ActionChip, 'llama3:8b'));
    expect(checked.last, {
      'provider': 'ollama',
      'model': 'llama3:8b',
      'base_url': 'http://localhost:11434',
    });
    await tap(tester, find.text('Enregistrer'));
    expect(checked, hasLength(2));
    expect(saved.last, {
      'provider': 'ollama',
      'model': 'llama3:8b',
      'base_url': 'http://localhost:11434',
    });
    expect(find.text('IA utilisée en ce moment : Ollama (sur ce PC) · llama3:8b'), findsOneWidget);

    // Claude : sans clé, rien à vérifier ; la clé collée est vérifiée avant l'enregistrement.
    await tap(tester, find.text('Claude (Anthropic)'));
    expect(find.text('Collez la clé : la vérification se lancera toute seule.'), findsOneWidget);
    expect(checked, hasLength(2));
    await tester.enterText(find.widgetWithText(TextField, 'Clé d\'API'), 'sk-ant-secret-1234');
    await tap(tester, find.text('Enregistrer'));
    expect(checked.last, {'provider': 'claude', 'api_key': 'sk-ant-secret-1234'});
    expect(saved.last, {'provider': 'claude', 'api_key': 'sk-ant-secret-1234'});
    expect(find.text('Clé enregistrée …1234 : laissez vide pour la garder.'), findsOneWidget);
    expect(find.text('sk-ant-secret-1234'), findsNothing);
    expect(find.textContaining('🔑 Clé enregistrée …1234'), findsOneWidget);

    // Retour à Ollama : son modèle est resté ; Claude garde sa clé pour plus tard.
    await tap(tester, find.text('Ollama (sur ce PC) · conseillé'));
    expect(find.widgetWithText(TextField, 'llama3:8b'), findsOneWidget);
    await tap(tester, find.text('Enregistrer'));
    expect(saved.last, {
      'provider': 'ollama',
      'model': 'llama3:8b',
      'base_url': 'http://localhost:11434',
    });
    await tap(tester, find.text('Claude (Anthropic)'));
    expect(find.text('Clé enregistrée …1234 : laissez vide pour la garder.'), findsOneWidget);
    await tap(tester, find.text('Enregistrer'));
    expect(saved.last, {'provider': 'claude'}); // la clé enregistrée sert, sans la ressaisir

    // Repli (§147) : si Claude ne répond pas, Ollama prend le relais — seulement si le parent le veut.
    final fallbackSwitch = find.widgetWithText(
      SwitchListTile,
      'Si cette IA ne répond pas, essayer mes autres IA enregistrées',
    );
    await tester.ensureVisible(fallbackSwitch);
    expect(tester.widget<SwitchListTile>(fallbackSwitch).value, isFalse);
    expect(find.textContaining('Ollama (sur ce PC) prend le relais'), findsOneWidget);
    await tester.tap(fallbackSwitch);
    await tester.pumpAndSettle();
    expect(saved.last, {'provider': 'claude', 'fallback': true}); // modèle et clé inchangés
    expect(tester.widget<SwitchListTile>(fallbackSwitch).value, isTrue);

    // Oublier la clé de Claude.
    await tap(tester, find.text('Oublier la clé de Claude (Anthropic)'));
    await tap(tester, find.text('Oublier'));
    expect(server.routes, contains('DELETE /v1/parent/ai/providers/claude'));
    expect(find.textContaining('🔑 Clé enregistrée'), findsNothing);
    expect(find.text('Collez la clé : la vérification se lancera toute seule.'), findsOneWidget);
  });

  for (final available in [true, false]) {
    testWidgets(
      'étape 24 : le parent permet les sites éducatifs (moteur de recherche : $available)',
      (tester) async {
        var webSources = false;
        Map<String, Object?> settings() => {
          'family': null,
          'saved': <Object>[],
          'server_provider': 'fake',
          'web_sources': webSources,
          'web_sources_available': available,
          'providers': [
            {
              'code': 'fake',
              'label': 'Démonstration (sans IA)',
              'note': '',
              'needs_key': false,
              'custom_url': false,
              'default_url': null,
              'default_model': null,
              'key_url': '',
              'recommended': true,
              'available': true,
            },
          ],
        };
        final sent = <Object?>[];
        server
          ..on('GET /v1/parent/ai', (_) => (200, settings()))
          ..on(
            'POST /v1/parent/ai/test',
            (_) => (200, {'ok': true, 'message': 'OK', 'models': <Object>[]}),
          )
          ..on('PUT /v1/parent/ai/sources', (r) {
            sent.add(r.data);
            webSources = (r.data as Map<String, dynamic>)['enabled'] as bool;
            return (200, settings());
          });
        final title = find.widgetWithText(
          SwitchListTile,
          '📚 Utiliser des sites éducatifs de confiance',
        );
        await launch(tester);
        await tap(tester, find.byTooltip('Mon compte'));
        await tap(tester, find.text('Intelligence artificielle'));
        await tester.ensureVisible(title);
        expect(tester.widget<SwitchListTile>(title).value, isFalse);
        if (!available) {
          // Pas de moteur de recherche sur le serveur : l'interrupteur dit comment l'installer.
          expect(tester.widget<SwitchListTile>(title).onChanged, isNull);
          expect(find.textContaining('Activer-Recherche-Ludifun.bat'), findsOneWidget);
          return;
        }
        expect(find.textContaining('des questions d\'entraînement s\'ajoutent'), findsOneWidget);
        expect(find.textContaining('jamais le prénom de l\'enfant ni sa photo'), findsOneWidget);
        await tester.tap(title);
        await tester.pumpAndSettle();
        expect(sent, [
          {'enabled': true},
        ]);
        expect(tester.widget<SwitchListTile>(title).value, isTrue);
      },
    );
  }

  testWidgets('une IA qui ne fonctionne pas : prévenu avant d\'enregistrer', (tester) async {
    final saved = <Object?>[];
    server
      ..on(
        'GET /v1/parent/ai',
        (_) => (
          200,
          {
            'family': null,
            'server_provider': 'ollama',
            'providers': [
              {
                'code': 'ollama',
                'label': 'Ollama (sur ce PC)',
                'note': '',
                'needs_key': false,
                'custom_url': true,
                'default_url': 'http://localhost:11434',
                'default_model': 'qwen2.5vl:7b',
                'key_url': '',
                'recommended': true,
                'available': true,
              },
            ],
          },
        ),
      )
      ..on(
        'POST /v1/parent/ai/test',
        (_) => (
          200,
          {
            'ok': false,
            'message': 'Service injoignable (ConnectError) : Ollama est-il lancé sur le PC ?',
            'models': <String>[],
          },
        ),
      )
      ..on('PUT /v1/parent/ai', (r) {
        saved.add(r.data);
        return (200, {'family': null, 'server_provider': 'ollama', 'providers': <Object>[]});
      });
    final container = await launch(tester);
    await go(tester, container, Routes.aiSettings);
    expect(
      find.text('⚠️ Service injoignable (ConnectError) : Ollama est-il lancé sur le PC ?'),
      findsOneWidget,
    );

    await tap(tester, find.text('Enregistrer'));
    expect(find.text('Cette IA ne fonctionne pas encore'), findsOneWidget);
    await tap(tester, find.text('Corriger'));
    expect(saved, isEmpty);

    await tap(tester, find.text('Enregistrer'));
    await tap(tester, find.text('Enregistrer quand même'));
    expect(saved, [
      {'provider': 'ollama', 'base_url': 'http://localhost:11434'},
    ]);
  });

  testWidgets('donner son avis (tests en famille)', (tester) async {
    final sent = <Object?>[];
    server.on('POST /v1/feedback', (r) {
      sent.add(r.data);
      return (201, {'id': 'f1'});
    });
    await launch(tester);
    await tap(tester, find.byTooltip('Mon compte'));
    await tap(tester, find.text('Donner mon avis'));
    expect(find.text('Ludifun vous est-il utile ?'), findsOneWidget);
    final send = find.widgetWithText(FilledButton, 'Envoyer');
    expect(tester.widget<FilledButton>(send).onPressed, isNull); // ni note ni message

    await tap(tester, find.byTooltip('4 sur 5'));
    await tester.enterText(find.byType(TextField), '  Emma adore les défis bonus.  ');
    await tap(tester, send);
    expect(sent, [
      {'rating': 4, 'message': 'Emma adore les défis bonus.', 'screen': 'parent_home'},
    ]);
    expect(find.text('Merci pour votre avis !'), findsOneWidget);
    expect(find.text('Ludifun vous est-il utile ?'), findsNothing);
  });

  testWidgets('compétences par leçon, avec ce qui manque encore', (tester) async {
    Map<String, Object?> level(int value, String label, String color) => {
      'value': value,
      'label': label,
      'color': color,
    };
    server.on(
      'GET /v1/children/c1/skills',
      (_) => (
        200,
        {
          'lessons': [
            {
              'lesson_id': 'l2',
              'title': 'Les fractions',
              'subject': 'math',
              'created_at': '2026-09-20T15:00:00Z',
              'skills': [
                {
                  'id': 'sk1',
                  'label': 'Comparer deux fractions de même dénominateur',
                  'verb': 'apply',
                  'importance': 5,
                  'level': level(3, 'En cours d\'acquisition', 'orange'),
                  'knowledge_ids': ['k2', 'k4'],
                },
              ],
              'notions': [
                {
                  'id': 'k1',
                  'label': 'Fraction',
                  'importance': 5,
                  'level': level(5, 'Très bien maîtrisée', 'green'),
                  'explanation': 'Maîtrisée et bien retenue dans le temps.',
                },
                {
                  'id': 'k2',
                  'label': 'Numérateur',
                  'importance': 5,
                  'level': level(4, 'Maîtrisée', 'green'),
                  'explanation': 'Maîtrisée : il reste à la garder en mémoire.',
                },
                {
                  'id': 'k4',
                  'label': 'Comparer des fractions',
                  'importance': 4,
                  'level': level(3, 'En cours d\'acquisition', 'orange'),
                  'explanation': 'Connaît la règle, doit encore s\'entraîner à l\'appliquer.',
                  'facts':
                      'Sur les 6 dernières activités : 3 réussies seul, 1 avec une aide, 2 ratées.',
                  'level_rates': [
                    {'level': 1, 'name': 'reconnaître', 'rate': 0.9},
                    {'level': 2, 'name': 'se rappeler', 'rate': 0.6},
                    {'level': 3, 'name': 'appliquer', 'rate': null},
                  ],
                  'independence': 0.75,
                },
              ],
            },
          ],
        },
      ),
    );
    await launch(tester);
    await tap(tester, find.text('Emma · CM1'));
    await tap(tester, find.text('Compétences par leçon'));

    expect(find.text('Compétences · Emma'), findsOneWidget);
    expect(find.text('📐 Les fractions'), findsOneWidget);
    expect(find.text('Comparer deux fractions de même dénominateur'), findsOneWidget);
    expect(find.text('En cours d\'acquisition · Appliquer'), findsOneWidget);
    // Notion reliée à aucune compétence : regroupée à part.
    expect(find.text('Autres notions'), findsOneWidget);

    await tap(tester, find.text('Comparer deux fractions de même dénominateur'));
    expect(find.text('Numérateur'), findsOneWidget);
    // Le fait observé, puis l'interprétation du moteur, à part (§131).
    expect(
      find.text('📊 Sur les 6 dernières activités : 3 réussies seul, 1 avec une aide, 2 ratées.'),
      findsOneWidget,
    );
    expect(
      find.text('Réussite par niveau : reconnaître 90 % · se rappeler 60 % · seul 75 %'),
      findsOneWidget,
    );
    expect(
      find.text('💬 Connaît la règle, doit encore s\'entraîner à l\'appliquer.'),
      findsOneWidget,
    );
    expect(find.text('Fraction'), findsNothing); // dans « Autres notions », encore fermé

    await tap(tester, find.byTooltip('Comment lire les niveaux'));
    expect(
      find.textContaining('« Maîtrisée » ne veut pas dire « réussit les QCM »'),
      findsOneWidget,
    );
    Navigator.of(tester.element(find.textContaining('« Maîtrisée »'))).pop();
    await tester.pumpAndSettle();

    // Supprimer une leçon : dans l'espace parent, après confirmation.
    server.on('DELETE /v1/lessons/l2', (r) {
      expect(r.queryParameters['child_id'], 'c1');
      return (204, null);
    });
    await tap(tester, find.byTooltip('Supprimer la leçon'));
    expect(find.text('Supprimer « Les fractions » ?'), findsOneWidget);
    server.on('GET /v1/children/c1/skills', (_) => (200, {'lessons': <Object?>[]}));
    await tap(tester, find.widgetWithText(FilledButton, 'Supprimer'));
    expect(server.routes, contains('DELETE /v1/lessons/l2'));
    expect(find.text('📐 Les fractions'), findsNothing);
  });

  testWidgets('étape 25 : le parent relit les questions d\'une leçon et en fait corriger', (
    tester,
  ) async {
    var version = 1;
    Map<String, Object?> notion() => {
      'knowledge_id': 'n1',
      'label': 'Numérateur',
      'statement': 'Le numérateur est le nombre du haut.',
      'blocks': [
        {
          'title': '❓ Questions à choix',
          'instruction': 'Lis la question, puis choisis la bonne réponse parmi les quatre.',
          'lines': [
            version == 1
                ? 'Quel terme désigne le nombre supérieur ?\n✅ Numérateur'
                : 'Dans 3/4, quel est le nombre du haut ?\n✅ 3',
          ],
        },
      ],
    };
    server
      ..on(
        'GET /v1/children/c1/lessons/l2/content',
        (_) => (
          200,
          {
            'lesson_id': 'l2',
            'title': 'Les fractions',
            'grade': 'CM1',
            'text': 'Une fraction a un numérateur et un dénominateur.',
            'notions': [notion()],
          },
        ),
      )
      ..on('POST /v1/children/c1/lessons/l2/notions/n1/rework', (r) {
        expect(r.data, {'reason': 'too_hard', 'comment': 'Des mots plus simples'});
        version = 2;
        return (200, notion());
      });
    final container = await launch(tester);
    await go(tester, container, Routes.lessonContent('c1', 'l2'));
    expect(find.text('Les fractions'), findsOneWidget);
    await tap(tester, find.text('Numérateur'));
    expect(find.text('Quel terme désigne le nombre supérieur ?\n✅ Numérateur'), findsOneWidget);
    expect(
      find.text(
        'Consigne lue par l\'enfant : « Lis la question, puis choisis la bonne réponse parmi les quatre. »',
      ),
      findsOneWidget,
    );
    await tap(tester, find.text('La leçon, telle que l\'IA l\'a lue'));
    expect(find.text('Une fraction a un numérateur et un dénominateur.'), findsOneWidget);

    await tap(tester, find.text('Demander une correction à l\'IA'));
    expect(
      tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Demander à l\'IA')).onPressed,
      isNull,
    );
    await tap(tester, find.text('Trop difficile'));
    await tester.enterText(find.byType(TextField), 'Des mots plus simples');
    await tap(tester, find.text('Demander à l\'IA'));
    expect(find.text('Nouvelles questions enregistrées.'), findsOneWidget);
    expect(server.routes, contains('POST /v1/children/c1/lessons/l2/notions/n1/rework'));
    // Rechargées : la notion reste ouverte, avec la nouvelle version.
    expect(find.text('Dans 3/4, quel est le nombre du haut ?\n✅ 3'), findsOneWidget);
  });

  testWidgets('étape 27 : le parent valide, refuse et fait refaire l\'image d\'une leçon', (
    tester,
  ) async {
    var status = 'to_review';
    Map<String, Object?> image() => {
      'status': status,
      'alt': 'Une pizza coupée en quatre parts',
      'remark': status == 'generating' ? 'Plus de couleurs' : null,
      'error': null,
      'url': status == 'generating' ? null : '/v1/children/c1/lessons/l2/image/file',
    };
    server
      ..on(
        'GET /v1/children/c1/lessons/l2/content',
        (_) => (
          200,
          {
            'lesson_id': 'l2',
            'title': 'Les fractions',
            'grade': 'CM1',
            'text': null,
            'notions': <Object?>[],
          },
        ),
      )
      ..on(
        'GET /v1/children/c1/lessons/l2/image',
        (_) => (200, {'available': true, 'image': image()}),
      )
      ..on('GET /v1/children/c1/lessons/l2/image/file', (_) => (200, tinyPng))
      ..on('POST /v1/children/c1/lessons/l2/image/approve', (_) {
        status = 'approved';
        return (200, image());
      })
      ..on('POST /v1/children/c1/lessons/l2/image/reject', (_) {
        status = 'rejected';
        return (200, image());
      })
      ..on('POST /v1/children/c1/lessons/l2/image/redo', (r) {
        expect(r.data, {'remark': 'Plus de couleurs'});
        status = 'generating';
        return (202, image());
      });
    final container = await launch(tester);
    await go(tester, container, Routes.lessonContent('c1', 'l2'));
    expect(find.textContaining('À valider'), findsOneWidget);
    expect(find.bySemanticsLabel('Une pizza coupée en quatre parts'), findsOneWidget);

    await tap(tester, find.text('Valider'));
    expect(find.textContaining('l\'enfant la verra avec sa leçon'), findsOneWidget);
    expect(find.text('Validée : l\'enfant la voit avec sa leçon.'), findsOneWidget);
    expect(find.text('Valider'), findsNothing);

    await tap(tester, find.text('Refuser'));
    expect(find.textContaining('Refusée'), findsOneWidget);

    await tap(tester, find.text('Refaire'));
    await tester.enterText(find.byType(TextField), 'Plus de couleurs');
    await tap(tester, find.widgetWithText(FilledButton, 'Refaire l\'image'));
    expect(server.routes, contains('POST /v1/children/c1/lessons/l2/image/redo'));
    expect(find.text('Image en préparation… (quelques minutes)'), findsOneWidget);
    expect(find.text('Votre remarque : « Plus de couleurs »'), findsOneWidget);

    // Prête : l'état est relu tout seul, la nouvelle image attend la validation.
    status = 'to_review';
    await tester.pump(const Duration(seconds: 11));
    await tester.pumpAndSettle();
    expect(find.textContaining('À valider'), findsOneWidget);
    expect(server.routes, contains('GET /v1/children/c1/lessons/l2/image/file'));
  });

  testWidgets('étape 30 : ressources des sites de confiance, masquer, regarder, chercher', (
    tester,
  ) async {
    var hidden = false;
    var searches = 0;
    Map<String, Object?> exercise() => {
      'id': 'r1',
      'provider': 'mathalea',
      'kind': 'exercise',
      'title': 'Opérations simples avec des fractions',
      'url': 'https://coopmaths.fr/alea/?uuid=f0f0f&v=eleve',
      'licence': 'MathALÉA, Coopmaths (logiciel libre AGPL)',
      'best': {'correct': 4, 'total': 5},
      'hidden': hidden,
      'attempts': 2,
      'last_done_at': '2026-09-23T15:00:00Z',
    };
    server
      ..on(
        'GET /v1/children/c1/lessons/l2/content',
        (_) => (
          200,
          {
            'lesson_id': 'l2',
            'title': 'Les fractions',
            'grade': 'CM1',
            'text': null,
            'notions': <Object?>[],
          },
        ),
      )
      ..on(
        'GET /v1/children/c1/lessons/l2/resources',
        (_) => (
          200,
          {
            'available': true,
            'resources': [exercise()],
          },
        ),
      )
      ..on('POST /v1/children/c1/lessons/l2/resources/r1/hide', (_) {
        hidden = true;
        return (200, exercise());
      })
      ..on('POST /v1/children/c1/lessons/l2/resources/prepare', (_) {
        searches++;
        return (202, {'available': true, 'resources': <Object?>[]});
      });
    final container = await launch(tester);
    await go(tester, container, Routes.lessonContent('c1', 'l2'));

    expect(find.text('Pour s\'entraîner autrement'), findsOneWidget);
    expect(find.text('Opérations simples avec des fractions'), findsOneWidget);
    expect(find.text('Exercice noté · MathALÉA · 2 essai(s) · meilleur score 4/5'), findsOneWidget);

    // Masquer : l'enfant ne la voit plus.
    await tap(tester, find.byType(Switch));
    expect(server.routes, contains('POST /v1/children/c1/lessons/l2/resources/r1/hide'));
    expect(
      find.text('Exercice noté · MathALÉA · masquée · 2 essai(s) · meilleur score 4/5'),
      findsOneWidget,
    );
    await tester.pump(const Duration(seconds: 5));
    await tester.pumpAndSettle();

    // Le parent regarde l'exercice dans l'application : aucun score n'est envoyé pour lui.
    await tap(tester, find.text('Opérations simples avec des fractions'));
    expect(find.text('Page : https://coopmaths.fr/alea/?uuid=f0f0f&v=eleve'), findsOneWidget);
    await tester.tap(find.text('Finir l\'exercice'));
    await tester.pumpAndSettle();
    expect(server.routes.where((r) => r.endsWith('/result')), isEmpty);
    await tap(tester, find.byType(BackButton));

    // Chercher de nouveau : la liste est relue un peu plus tard.
    final reads = server.routes.where((r) => r.endsWith('/l2/resources')).length;
    await tap(tester, find.text('Chercher des ressources'));
    expect(searches, 1);
    await tester.pump(const Duration(seconds: 41));
    await tester.pumpAndSettle();
    expect(server.routes.where((r) => r.endsWith('/l2/resources')).length, greaterThan(reads + 1));
  });

  testWidgets('étape 28 : images des notions, « pas utile », préparer et tout valider', (
    tester,
  ) async {
    var prepared = false;
    final approved = <String>{};
    Map<String, Object?> picture(String id, String label) => {
      'id': id,
      'status': approved.contains(id) ? 'approved' : 'to_review',
      'alt': 'Une image de $label',
      'remark': null,
      'error': null,
      'url': '/v1/children/c1/lessons/l2/images/$id/file',
      'knowledge_id': 'k-$id',
      'label': label,
    };
    server
      ..on(
        'GET /v1/children/c1/lessons/l2/content',
        (_) => (
          200,
          {
            'lesson_id': 'l2',
            'title': 'Les fractions',
            'grade': 'CM1',
            'text': null,
            'notions': <Object?>[],
          },
        ),
      )
      ..on(
        'GET /v1/children/c1/lessons/l2/image',
        (_) => (
          200,
          {
            'available': true,
            'image': prepared
                ? {
                    'id': 'cover',
                    'status': 'not_needed',
                    'alt': null,
                    'remark': null,
                    'error': 'Un calcul ne se dessine pas.',
                    'url': null,
                  }
                : null,
            'pictures': prepared
                ? [picture('i1', 'Le volcan'), picture('i2', 'La lave')]
                : <Object?>[],
          },
        ),
      )
      ..on('POST /v1/children/c1/lessons/l2/images/prepare', (_) {
        prepared = true;
        return (202, {'status': 'generating'});
      })
      ..on('GET /v1/children/c1/lessons/l2/images/i1/file', (_) => (200, tinyPng))
      ..on('GET /v1/children/c1/lessons/l2/images/i2/file', (_) => (200, tinyPng));
    for (final id in ['i1', 'i2']) {
      server.on('POST /v1/children/c1/lessons/l2/images/$id/approve', (_) {
        approved.add(id);
        return (200, picture(id, id));
      });
    }
    final container = await launch(tester);
    await go(tester, container, Routes.lessonContent('c1', 'l2'));
    expect(find.textContaining('L\'IA ne dessine que si une image aide'), findsOneWidget);
    await tap(tester, find.text('Préparer les images'));
    expect(server.routes, contains('POST /v1/children/c1/lessons/l2/images/prepare'));
    expect(find.textContaining('l\'IA dit d\'abord si elles aident'), findsOneWidget);

    // L'image de la leçon n'aiderait pas ; les notions concrètes ont la leur, à valider.
    expect(
      find.text(
        'Pas utile pour cette leçon : Un calcul ne se dessine pas.. '
        'Vous pouvez en demander une quand même.',
      ),
      findsOneWidget,
    );
    expect(find.text('Créer quand même'), findsOneWidget);
    expect(find.text('Images pour apprendre'), findsOneWidget);
    expect(find.text('Le volcan'), findsOneWidget);
    expect(find.text('La lave'), findsOneWidget);
    await tap(tester, find.text('Valider les 2 images'));
    expect(approved, {'i1', 'i2'});
    expect(
      find.text('Validée : l\'enfant la voit avec la notion et dans les jeux en images.'),
      findsNWidgets(2),
    );
  });

  testWidgets('le parent voit les erreurs d\'Emma aux questions', (tester) async {
    server.on(
      'GET /v1/children/c1/mistakes',
      (r) => (
        200,
        {
          'mistakes': [
            {
              'answered_at': '2026-09-20T15:00:00Z',
              'lesson_id': 'l2',
              'lesson_title': 'Les fractions',
              'subject': 'math',
              'activity_type': 'MCQ',
              'notions': ['Numérateur'],
              'question': 'Dans 3/4, quel nombre est le numérateur ?',
              'given': '4',
              'expected': '3',
              'partial': false,
            },
          ],
          'next_before': null,
        },
      ),
    );
    await launch(tester);
    await tap(tester, find.text('Emma · CM1'));
    await tap(tester, find.text('Voir ses erreurs aux questions'));

    expect(find.text('Erreurs d\'Emma'), findsOneWidget);
    expect(ofName('Léo'), 'de Léo');
    expect(find.text('Dans 3/4, quel nombre est le numérateur ?'), findsOneWidget);
    expect(find.text('❌ Sa réponse'), findsOneWidget);
    expect(find.text('✅ Bonne réponse'), findsOneWidget);
    expect(find.text('Notion : Numérateur'), findsOneWidget);
    expect(find.text('Voir les erreurs plus anciennes'), findsNothing);
  });

  testWidgets('objectifs : temps par jour, matière, contrôle et son plan', (tester) async {
    final patches = <Object?>[];
    var exams = <Map<String, Object?>>[
      {
        'id': 'e1',
        'title': 'Contrôle d\'histoire',
        'exam_date': '2026-09-26',
        'lesson_ids': ['l1'],
        'plan': [
          {
            'day': '2026-09-23',
            'focus': 'diagnostic',
            'label': 'Où en es-tu ? Un tour de toute la leçon',
            'done': true,
          },
          {
            'day': '2026-09-25',
            'focus': 'mock_test',
            'label': 'Mini-contrôle : comme le jour J',
            'done': false,
          },
        ],
      },
    ];
    server
      ..on('GET /v1/children/c1/exams', (_) => (200, exams))
      ..on('PATCH /v1/children/c1', (r) {
        patches.add(r.data);
        emmaChild = {...emmaChild, ...(r.data as Map<String, dynamic>)};
        return (200, emmaChild);
      })
      ..on('DELETE /v1/children/c1/exams/e1', (_) {
        exams = [];
        return (204, null);
      })
      ..on(
        'GET /v1/lessons',
        (r) => (
          200,
          [
            {
              'id': 'l1',
              'status': 'ready',
              'failure_reason': null,
              'subject': 'history',
              'title': 'La Révolution française',
              'created_at': '2026-09-20T15:00:00Z',
            },
          ],
        ),
      );
    await launch(tester);
    await tap(tester, find.text('Emma · CM1'));
    await tap(tester, find.text('Objectifs et contrôles'));

    expect(find.text('Objectifs · Emma'), findsOneWidget);
    await tap(tester, find.text('15 min'));
    await tap(tester, find.text('📐 Mathématiques'));
    expect(patches, [
      {'daily_minutes': 15, 'priority_subject': null},
      {'daily_minutes': 15, 'priority_subject': 'math'},
    ]);
    await tap(tester, find.text('Libre'));
    expect(patches.last, {'daily_minutes': null, 'priority_subject': 'math'});

    // Le plan : l'étape faite est cochée.
    expect(find.text('📅 Contrôle d\'histoire · samedi 26 septembre'), findsOneWidget);
    expect(
      find.text('✅ Mercredi 23 septembre : Où en es-tu ? Un tour de toute la leçon'),
      findsOneWidget,
    );
    expect(find.text('▫️ Vendredi 25 septembre : Mini-contrôle : comme le jour J'), findsOneWidget);
    await tap(tester, find.byTooltip('Supprimer ce contrôle'));
    expect(find.textContaining('Ajoutez un contrôle'), findsOneWidget);

    // Nouveau contrôle : titre, leçon, date.
    server.on('POST /v1/children/c1/exams', (r) {
      final body = r.data as Map<String, dynamic>;
      expect(body['title'], 'Contrôle de la Révolution');
      expect(body['lesson_ids'], ['l1']);
      exams = [
        {
          'id': 'e2',
          'title': body['title'],
          'exam_date': body['exam_date'],
          'lesson_ids': ['l1'],
          'plan': <Object>[],
        },
      ];
      return (201, exams.single);
    });
    await tap(tester, find.text('Ajouter un contrôle'));
    final save = find.widgetWithText(FilledButton, 'Enregistrer le contrôle');
    await tester.enterText(find.byType(TextField), 'Contrôle de la Révolution');
    await tap(tester, find.text('🏛️ La Révolution française'));
    expect(tester.widget<FilledButton>(save).onPressed, isNull); // pas encore de date
    await tap(tester, find.text('Choisir la date'));
    await tap(tester, find.text('OK'));
    await tap(tester, save);
    expect(server.routes, contains('POST /v1/children/c1/exams'));
    expect(find.textContaining('📅 Contrôle de la Révolution'), findsOneWidget);
  });

  testWidgets('exporter les données d\'Emma (RGPD)', (tester) async {
    final export = {
      'format': 'ludifun-export-v1',
      'child': {'display_name': 'Emma'},
      'lessons': <Object>[],
    };
    server
      ..on(
        'GET /v1/children/c1/history',
        (_) => (200, {'sessions': <Object>[], 'next_before': null}),
      )
      ..on('GET /v1/children/c1/devices', (_) => (200, <Object>[]))
      ..on(
        'GET /v1/children/c1/export',
        (_) => (200, export),
        headers: {'content-disposition': 'attachment; filename="ludifun-c1-2026-09-24.json"'},
      );
    final container = await launch(tester);
    await go(tester, container, Routes.childSettings('c1'));

    await tap(tester, find.text('Exporter les données de Emma'));
    final file = sharer.shared.single;
    expect(file.filename, 'ludifun-c1-2026-09-24.json');
    expect(file.mimeType, 'application/json');
    expect(file.subject, 'Données Ludifun de Emma');
    expect(jsonDecode(utf8.decode(file.bytes)), export);

    // Erreur du serveur : message, et le bouton redevient utilisable.
    server.on(
      'GET /v1/children/c1/export',
      (_) => FakeServer.error(404, 'child_not_found', 'Enfant introuvable.'),
    );
    await tap(tester, find.text('Exporter les données de Emma'));
    expect(find.text('Enfant introuvable.'), findsOneWidget);
    expect(sharer.shared, hasLength(1));
  });
}
