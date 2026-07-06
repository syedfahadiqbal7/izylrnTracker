class Child {
  final String id;
  final String name;
  final String? nickname;
  final String? photoUrl;
  final String? schoolName;
  final String? classGrade;
  final int deviceCount;
  final String? role; // requesting parent's role (permissions.role)

  Child({
    required this.id,
    required this.name,
    required this.nickname,
    required this.photoUrl,
    required this.schoolName,
    required this.classGrade,
    required this.deviceCount,
    required this.role,
  });

  factory Child.fromJson(Map<String, dynamic> j) => Child(
        id: j['id'] as String,
        name: j['name'] as String,
        nickname: j['nickname'] as String?,
        photoUrl: j['photo_url'] as String?,
        schoolName: j['school_name'] as String?,
        classGrade: j['class_grade'] as String?,
        deviceCount: (j['device_count'] ?? 0) as int,
        role: (j['permissions'] as Map<String, dynamic>?)?['role'] as String?,
      );

  String get initials {
    final parts =
        name.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
    if (parts.isEmpty) return '?';
    if (parts.length == 1) return parts.first.substring(0, 1).toUpperCase();
    return (parts.first.substring(0, 1) + parts.last.substring(0, 1))
        .toUpperCase();
  }
}
