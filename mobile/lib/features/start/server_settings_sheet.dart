import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme.dart';
import '../../core/config.dart';
import '../../core/session.dart';

/// Vérifie qu'une API répond à cette adresse ; rend un détail affichable.
final serverProbeProvider = Provider<Future<String> Function(String url)>((ref) => probeServer);

Future<String> probeServer(String url) async {
  final dio = Dio(
    BaseOptions(
      connectTimeout: const Duration(seconds: 5),
      receiveTimeout: const Duration(seconds: 5),
    ),
  );
  final r = await dio.get<Map<String, dynamic>>('$url/health/ready');
  return 'schéma ${r.data?['schema'] ?? '?'}';
}

/// Versions de test : adresse de l'API (l'ordinateur qui fait tourner `docker compose`).
class ServerSettingsSheet extends ConsumerStatefulWidget {
  const ServerSettingsSheet({super.key});

  @override
  ConsumerState<ServerSettingsSheet> createState() => _ServerSettingsSheetState();
}

class _ServerSettingsSheetState extends ConsumerState<ServerSettingsSheet> {
  late final _url = TextEditingController(text: ref.read(apiBaseUrlProvider));
  String? _status;
  bool _ok = false;
  bool _busy = false;

  @override
  void dispose() {
    _url.dispose();
    super.dispose();
  }

  void _show(bool ok, String status) => setState(() {
    _ok = ok;
    _status = status;
  });

  Future<String?> _check() async {
    final url = normalizeApiUrl(_url.text);
    if (url == null) {
      _show(false, 'Adresse illisible. Exemple : 192.168.1.20:8000');
      return null;
    }
    setState(() {
      _busy = true;
      _status = null;
    });
    try {
      final detail = await ref.read(serverProbeProvider)(url);
      _show(true, '✅ Serveur joignable ($detail)');
      return url;
    } on Exception {
      _show(
        false,
        'Serveur injoignable. Vérifiez que le téléphone et l\'ordinateur sont sur le même '
        'Wi-Fi, que l\'API tourne et que le pare-feu autorise le port 8000.',
      );
      return null;
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _save() async {
    final url = await _check();
    if (url == null) return;
    await ref.read(apiBaseUrlProvider.notifier).set(url);
    if (mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.fromLTRB(24, 24, 24, 24 + MediaQuery.viewInsetsOf(context).bottom),
    child: Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Serveur de test', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        const Text(
          'Adresse de l\'ordinateur qui fait tourner l\'API (docker compose), sur le même Wi-Fi.',
        ),
        const SizedBox(height: 16),
        TextField(
          controller: _url,
          keyboardType: TextInputType.url,
          autocorrect: false,
          decoration: const InputDecoration(
            labelText: 'Adresse du serveur',
            hintText: 'http://192.168.1.20:8000',
          ),
        ),
        if (_status != null) ...[
          const SizedBox(height: 12),
          Text(
            _status!,
            style: TextStyle(color: _ok ? LudiColors.mastered : LudiColors.notMastered),
          ),
        ],
        const SizedBox(height: 16),
        Row(
          children: [
            Expanded(
              child: OutlinedButton(onPressed: _busy ? null : _check, child: const Text('Tester')),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: FilledButton(
                onPressed: _busy ? null : _save,
                child: const Text('Enregistrer'),
              ),
            ),
          ],
        ),
      ],
    ),
  );
}
