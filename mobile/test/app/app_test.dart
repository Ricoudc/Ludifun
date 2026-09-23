import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ludifun/app/app.dart';
import 'package:ludifun/core/storage/credentials.dart';

import '../support/fake_server.dart';

/// Critère de fin de l'étape 9 : l'application démarre dans les deux espaces.
void main() {
  late FakeServer server;
  setUp(
    () => server = FakeServer()
      ..on('GET /v1/me/mission', (_) => (200, {'lesson': null}))
      ..on('GET /v1/lessons', (_) => (200, <Object>[])),
  );

  Future<void> launch(WidgetTester tester, MemoryCredentialStore store) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: overridesFor(server, store),
        retry: noRetry,
        child: const LudifunApp(),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('premier lancement : l\'enfant relie sa tablette avec le code', (tester) async {
    final store = MemoryCredentialStore();
    server
      ..on('POST /v1/link', (r) {
        final body = r.data as Map<String, dynamic>;
        return body['code'] == '482731'
            ? (201, {'token': 'ldf_d_new', 'device_id': 'd1', 'child': emma})
            : FakeServer.error(400, 'invalid_link_code', 'Ce code ne marche pas.');
      })
      ..on('GET /v1/me', (_) => (200, emma));
    await launch(tester, store);
    expect(find.text('Qui utilise cet appareil ?'), findsOneWidget);

    await tester.tap(find.text('Je suis un enfant'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '111111');
    await tester.pumpAndSettle();
    expect(find.text('Ce code ne marche pas.'), findsOneWidget);
    expect(store.credentials, isA<NoCredentials>());

    await tester.enterText(find.byType(TextField), '482731'); // envoyé dès le 6e chiffre
    await tester.pumpAndSettle();
    await tester.tap(find.text('Oui, c\'est moi !'));
    await tester.pumpAndSettle();
    expect(find.text('Bonjour Emma ! 👋'), findsOneWidget);
    expect(find.text('🎯 Ta mission du jour'), findsOneWidget);
    expect((store.credentials as ChildCredentials).deviceToken, 'ldf_d_new');
    expect(bearer(server.requests.last), 'Bearer ldf_d_new');
  });

  testWidgets('premier lancement : le parent se connecte et voit ses enfants', (tester) async {
    final store = MemoryCredentialStore();
    server
      ..on('POST /v1/auth/login', (_) => (200, tokens('a1', 'r1')))
      ..on(
        'GET /v1/children',
        (_) => (
          200,
          [
            {...emma, 'created_at': '2026-09-01T10:00:00Z', 'devices': 1},
          ],
        ),
      );
    await launch(tester, store);

    await tester.tap(find.text('Je suis un parent'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Me connecter'));
    await tester.pumpAndSettle();
    expect(find.text('Saisissez une adresse e-mail valide.'), findsOneWidget);
    expect(server.requests, isEmpty);

    await tester.enterText(
      find.widgetWithText(TextFormField, 'Adresse e-mail'),
      'parent@example.fr',
    );
    await tester.enterText(find.widgetWithText(TextFormField, 'Mot de passe'), 'un mot de passe');
    await tester.tap(find.text('Me connecter'));
    await tester.pumpAndSettle();
    expect(find.text('Mes enfants'), findsOneWidget);
    expect(find.text('Emma · CM1'), findsOneWidget);
    expect(find.text('📱 1 appareil lié'), findsOneWidget);
    expect(store.credentials, isA<ParentCredentials>());
  });

  testWidgets('inscription : la politique de confidentialité doit être acceptée', (tester) async {
    final store = MemoryCredentialStore();
    server
      ..on('POST /v1/auth/register', (r) {
        expect((r.data as Map<String, dynamic>)['accepted_privacy_policy'], isTrue);
        return (201, tokens('a1', 'r1'));
      })
      ..on('GET /v1/children', (_) => (200, <Object>[]));
    await launch(tester, store);
    await tester.tap(find.text('Je suis un parent'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Créer un compte parent'));
    await tester.pumpAndSettle();

    await tester.enterText(
      find.widgetWithText(TextFormField, 'Adresse e-mail'),
      'parent@example.fr',
    );
    await tester.enterText(find.widgetWithText(TextFormField, 'Mot de passe'), 'trop court');
    await tester.tap(find.text('Créer mon compte'));
    await tester.pumpAndSettle();
    expect(find.text('Au moins 12 caractères.'), findsOneWidget); // l'erreur remplace l'aide

    await tester.enterText(
      find.widgetWithText(TextFormField, 'Mot de passe'),
      'un mot de passe solide',
    );
    await tester.tap(find.text('Créer mon compte'));
    await tester.pumpAndSettle();
    expect(
      find.text('Acceptez la politique de confidentialité pour créer votre compte.'),
      findsOneWidget,
    );
    expect(server.requests, isEmpty);

    await tester.tap(find.byType(CheckboxListTile));
    await tester.tap(find.text('Créer mon compte'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Ajoutez le profil de votre enfant'), findsOneWidget);
  });

  testWidgets('parent déjà connecté : espace parent direct, puis déconnexion', (tester) async {
    final store = MemoryCredentialStore(
      const ParentCredentials(accessToken: 'a1', refreshToken: 'r1', email: 'parent@example.fr'),
    );
    server
      ..on('GET /v1/children', (_) => (200, <Object>[]))
      ..on('POST /v1/auth/logout', (_) => (204, null));
    await launch(tester, store);
    expect(find.text('Mes enfants'), findsOneWidget);

    await tester.tap(find.byTooltip('Mon compte'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Me déconnecter'));
    await tester.pumpAndSettle();
    expect(find.text('Qui utilise cet appareil ?'), findsOneWidget);
    expect(server.routes, contains('POST /v1/auth/logout'));
    expect(store.credentials, isA<NoCredentials>());
  });

  testWidgets('enfant déjà lié : espace enfant direct ; appareil délié → premier lancement', (
    tester,
  ) async {
    const child = ChildCredentials(deviceToken: 'ldf_d_x', childId: 'c1', displayName: 'Emma');
    server.on('GET /v1/me', (_) => (200, emma));
    await launch(tester, MemoryCredentialStore(child));
    expect(find.text('Bonjour Emma ! 👋'), findsOneWidget);

    server.on('GET /v1/me', (_) => FakeServer.error(401, 'unauthorized', 'Appareil délié.'));
    final store = MemoryCredentialStore(child);
    await launch(tester, store);
    expect(find.text('Qui utilise cet appareil ?'), findsOneWidget);
    expect(store.credentials, isA<NoCredentials>());
  });

  testWidgets('un enfant ne peut pas ouvrir l\'espace parent', (tester) async {
    server.on('GET /v1/me', (_) => (200, emma));
    await launch(
      tester,
      MemoryCredentialStore(
        const ChildCredentials(deviceToken: 'ldf_d_x', childId: 'c1', displayName: 'Emma'),
      ),
    );
    await tester.binding.handlePushRoute('/parent');
    await tester.pumpAndSettle();
    expect(find.text('Mes enfants'), findsNothing);
    expect(find.text('Bonjour Emma ! 👋'), findsOneWidget);
  });
}
