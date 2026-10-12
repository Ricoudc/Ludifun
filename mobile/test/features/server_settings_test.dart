import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ludifun/app/app.dart';
import 'package:ludifun/core/config.dart';
import 'package:ludifun/core/session.dart';
import 'package:ludifun/core/storage/credentials.dart';
import 'package:ludifun/features/start/server_settings_sheet.dart';

import '../support/fake_server.dart';

void main() {
  test('adresse du serveur : saisie tolérante', () {
    expect(normalizeApiUrl('192.168.1.20:8000'), 'http://192.168.1.20:8000');
    expect(normalizeApiUrl(' http://192.168.1.20:8000/ '), 'http://192.168.1.20:8000');
    expect(normalizeApiUrl('https://api.ludifun.fr/docs?x=1'), 'https://api.ludifun.fr');
    expect(normalizeApiUrl(''), isNull);
    expect(normalizeApiUrl('ftp://serveur'), isNull);
    expect(normalizeApiUrl('http://'), isNull);
  });

  testWidgets('version de test : l\'adresse se vérifie puis s\'enregistre sur le téléphone', (
    tester,
  ) async {
    FlutterSecureStorage.setMockInitialValues({});
    final probed = <String>[];
    var reachable = false;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...overridesFor(FakeServer(), MemoryCredentialStore()),
          serverProbeProvider.overrideWithValue((url) async {
            probed.add(url);
            if (!reachable) throw Exception('injoignable');
            return 'schéma 0002';
          }),
        ],
        retry: noRetry,
        child: const LudifunApp(),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('Serveur de test : '), findsOneWidget);

    await tester.ensureVisible(find.textContaining('Serveur de test : '));
    await tester.tap(find.textContaining('Serveur de test : '));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '192.168.1.20:8000');
    await tester.tap(find.text('Enregistrer'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Serveur injoignable'), findsOneWidget); // rien n'est enregistré
    expect(await readSavedApiUrl(), isNull);

    reachable = true;
    await tester.tap(find.text('Tester'));
    await tester.pumpAndSettle();
    expect(find.text('✅ Serveur joignable (schéma 0002)'), findsOneWidget);
    await tester.tap(find.text('Enregistrer'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.textContaining('Serveur de test : '));
    expect(find.text('Serveur de test : http://192.168.1.20:8000'), findsOneWidget);
    expect(await readSavedApiUrl(), 'http://192.168.1.20:8000');
    expect(probed, everyElement('http://192.168.1.20:8000'));

    final container = ProviderScope.containerOf(tester.element(find.byType(LudifunApp)));
    expect(container.read(apiBaseUrlProvider), 'http://192.168.1.20:8000');
  });
}
