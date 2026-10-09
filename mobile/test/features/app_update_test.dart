import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ludifun/app/app.dart';
import 'package:ludifun/core/app_update.dart';
import 'package:ludifun/core/session.dart';
import 'package:ludifun/core/storage/credentials.dart';

import '../support/fake_server.dart';

const parent = ParentCredentials(accessToken: 'a1', refreshToken: 'r1', email: 'parent@example.fr');

/// §5.50 : le serveur de la maison propose la nouvelle application du téléphone.
void main() {
  late FakeServer server;
  late FakeLinkOpener links;

  setUp(() {
    links = FakeLinkOpener();
    server = FakeServer()..on('GET /v1/children', (_) => (200, <Object>[]));
  });

  Future<void> launch(WidgetTester tester, {required int build}) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.5;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...overridesFor(server, MemoryCredentialStore(parent), links),
          appBuildProvider.overrideWithValue(build),
        ],
        retry: noRetry,
        child: const LudifunApp(),
      ),
    );
    await tester.pumpAndSettle();
  }

  void serve(Object? build, {String url = '/v1/app/ludifun.apk'}) =>
      server.on('GET /v1/app/latest', (_) => (200, {'build': build, 'size': 1000, 'url': url}));

  testWidgets('version plus récente sur le serveur : bandeau, puis téléchargement', (tester) async {
    serve(412);
    await launch(tester, build: 400);
    expect(find.text('📲 Une nouvelle version de Ludifun est prête.'), findsOneWidget);
    await tester.tap(find.text('Mettre à jour'));
    await tester.pumpAndSettle();
    expect(links.opened, [Uri.parse('http://api.test/v1/app/ludifun.apk')]);
  });

  testWidgets('même version, version inconnue, rien à donner : pas de bandeau', (tester) async {
    for (final build in [400, null]) {
      serve(build);
      await launch(tester, build: 400);
      expect(find.text('Mettre à jour'), findsNothing);
    }
    server.handlers.remove('GET /v1/app/latest'); // 404 : serveur sans application
    await launch(tester, build: 400);
    expect(find.text('Mettre à jour'), findsNothing);
  });

  testWidgets('application construite à la main (numéro 0) : ne demande même pas', (tester) async {
    serve(412);
    await launch(tester, build: 0);
    expect(find.text('Mettre à jour'), findsNothing);
    expect(server.routes, isNot(contains('GET /v1/app/latest')));
  });

  test('une adresse qui sortirait du serveur est refusée', () async {
    final container = ProviderContainer(
      overrides: overridesFor(server, MemoryCredentialStore(parent)),
      retry: noRetry,
    );
    addTearDown(container.dispose);
    await container.read(sessionProvider.future);
    final api = container.read(apiProvider);
    for (final url in ['@autre-site.fr/app.apk', '/v1/../secret', 'https://autre.fr/a.apk']) {
      serve(9, url: url);
      expect(await api.latestApp(), isNull, reason: url);
    }
    serve(9);
    expect(await api.latestApp(), (build: 9, url: '/v1/app/ludifun.apk'));
  });
}
