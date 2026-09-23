import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api/api_client.dart';
import 'api/models.dart';
import 'screens/home_screen.dart';
import 'screens/onboarding_screen.dart';

final api = ApiClient();

void main() => runApp(const LudifunApp());

class LudifunApp extends StatelessWidget {
  const LudifunApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Ludifun',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF6C4AB6),
        useMaterial3: true,
        textTheme: Typography.material2021().black.apply(fontSizeFactor: 1.1),
      ),
      home: const _Root(),
    );
  }
}

/// Affiche l'accueil si un profil enfant existe, sinon l'écran de création.
class _Root extends StatefulWidget {
  const _Root();

  @override
  State<_Root> createState() => _RootState();
}

class _RootState extends State<_Root> {
  static const _childKey = 'child_id';
  Child? _child;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    final id = prefs.getInt(_childKey);
    Child? child;
    if (id != null) {
      try {
        child = await api.getChild(id);
      } on ApiException {
        await prefs.remove(_childKey);
      } catch (_) {
        // Serveur injoignable : on reste sur l'écran de création.
      }
    }
    setState(() {
      _child = child;
      _loading = false;
    });
  }

  Future<void> _onCreated(Child child) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(_childKey, child.id);
    setState(() => _child = child);
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Scaffold(body: Center(child: CircularProgressIndicator()));
    final child = _child;
    return child == null ? OnboardingScreen(onCreated: _onCreated) : HomeScreen(child: child);
  }
}
