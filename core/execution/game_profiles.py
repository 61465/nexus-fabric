"""
execution/game_profiles.py
═══════════════════════════
Database of known game engines and their optimization config keys.
Each profile maps quality tiers to specific engine INI overrides.
"""

from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────
#  Quality Tier → Config Mapping
# ─────────────────────────────────────────────────────────────────────

QUALITY_TIERS = {
    "ULTRA_PERFORMANCE": 0,
    "PERFORMANCE":       1,
    "BALANCED":          2,
    "QUALITY":           3,
    "ULTRA_QUALITY":     4,
}


@dataclass
class EngineProfile:
    engine:       str
    config_paths: list[str]   # Relative paths tried in order (% = env var)
    config_keys:  dict        # tier -> {section: {key: value}}
    backup_ext:   str = ".nexus_bak"
    safe_to_inject: bool = True
    notes: str = ""


@dataclass
class GameProfile:
    name:          str
    engine_name:   str
    process_names: list[str]
    anti_cheat:    bool = False
    multiplayer:   bool = False
    notes:         str = ""


# ─────────────────────────────────────────────────────────────────────
#  Engine Profiles
# ─────────────────────────────────────────────────────────────────────

ENGINE_PROFILES: dict[str, EngineProfile] = {

    "UnrealEngine4": EngineProfile(
        engine="Unreal Engine 4",
        config_paths=[
            "%LOCALAPPDATA%\\{game}\\Saved\\Config\\WindowsNoEditor\\Engine.ini",
            "%LOCALAPPDATA%\\{game}\\Saved\\Config\\Windows\\Engine.ini",
        ],
        config_keys={
            "ULTRA_PERFORMANCE": {
                "SystemSettings": {
                    "r.ShadowQuality":           "0",
                    "r.ScreenPercentage":         "50",
                    "sg.ShadowQuality":           "0",
                    "sg.EffectsQuality":          "0",
                    "sg.FoliageQuality":          "0",
                    "r.Streaming.PoolSize":       "256",
                    "r.DepthOfFieldQuality":      "0",
                    "r.BloomQuality":             "0",
                    "r.AmbientOcclusionLevels":   "0",
                    "r.VolumetricFog":            "0",
                    "r.LensFlareQuality":         "0",
                    "r.SceneColorFringeQuality":  "0",
                    "r.DetailMode":               "0",
                    "r.MipMapLODBias":            "4",
                    "r.MaxAnisotropy":            "4",
                    "foliage.DitheredLOD":        "0",
                    "r.DynamicGlobalIlluminationMethod": "0",
                },
            },
            "PERFORMANCE": {
                "SystemSettings": {
                    "r.ShadowQuality":           "0",
                    "r.ScreenPercentage":         "60",
                    "sg.ShadowQuality":           "0",
                    "sg.EffectsQuality":          "1",
                    "r.Streaming.PoolSize":       "512",
                    "r.DepthOfFieldQuality":      "0",
                    "r.AmbientOcclusionLevels":   "0",
                    "r.VolumetricFog":            "0",
                    "r.DetailMode":               "1",
                    "r.MipMapLODBias":            "2",
                    "r.MaxAnisotropy":            "8",
                    "r.DynamicGlobalIlluminationMethod": "0",
                },
            },
            "BALANCED": {
                "SystemSettings": {
                    "r.ShadowQuality":           "1",
                    "r.ScreenPercentage":         "75",
                    "sg.ShadowQuality":           "1",
                    "r.Streaming.PoolSize":       "1024",
                    "r.MipMapLODBias":            "1",
                    "r.MaxAnisotropy":            "8",
                    "r.DynamicGlobalIlluminationMethod": "1",
                },
            },
            "QUALITY": {
                "SystemSettings": {
                    "r.ShadowQuality":     "3",
                    "r.ScreenPercentage":  "90",
                    "sg.ShadowQuality":    "3",
                    "r.Streaming.PoolSize":"2048",
                    "r.MaxAnisotropy":     "16",
                },
            },
            "ULTRA_QUALITY": {
                "SystemSettings": {
                    "r.ShadowQuality":     "5",
                    "r.ScreenPercentage":  "100",
                    "sg.ShadowQuality":    "5",
                    "r.Streaming.PoolSize":"4096",
                    "r.MaxAnisotropy":     "16",
                    "r.Lumen.DiffuseIndirect.Allow": "1",
                    "r.RayTracing.Reflections": "1",
                },
            },
        },
    ),

    "UnrealEngine5": EngineProfile(
        engine="Unreal Engine 5",
        config_paths=[
            "%LOCALAPPDATA%\\{game}\\Saved\\Config\\Windows\\Engine.ini",
            "%LOCALAPPDATA%\\{game}\\Saved\\Config\\WindowsNoEditor\\Engine.ini",
        ],
        config_keys={
            "ULTRA_PERFORMANCE": {
                "SystemSettings": {
                    "r.ShadowQuality":           "0",
                    "r.ScreenPercentage":         "50",
                    "sg.ShadowQuality":           "0",
                    "sg.EffectsQuality":          "0",
                    "r.Streaming.PoolSize":       "256",
                    "r.MipMapLODBias":            "4",
                    "r.Lumen.DiffuseIndirect.Allow": "0",
                    "r.Nanite":                  "0",
                    "r.VolumetricFog":            "0",
                    "r.AmbientOcclusionLevels":   "0",
                    "r.DynamicGlobalIlluminationMethod": "0",
                },
            },
            "PERFORMANCE": {
                "SystemSettings": {
                    "r.ShadowQuality":           "0",
                    "r.ScreenPercentage":         "60",
                    "r.Streaming.PoolSize":       "512",
                    "r.MipMapLODBias":            "2",
                    "r.Lumen.DiffuseIndirect.Allow": "0",
                    "r.Nanite":                  "1",
                    "r.VolumetricFog":            "0",
                    "r.DynamicGlobalIlluminationMethod": "0",
                },
            },
            "BALANCED": {
                "SystemSettings": {
                    "r.ShadowQuality":           "1",
                    "r.ScreenPercentage":         "75",
                    "r.Streaming.PoolSize":       "1024",
                    "r.Lumen.DiffuseIndirect.Allow": "1",
                    "r.Nanite":                  "1",
                    "r.DynamicGlobalIlluminationMethod": "1",
                },
            },
            "QUALITY": {
                "SystemSettings": {
                    "r.ShadowQuality":     "3",
                    "r.ScreenPercentage":  "90",
                    "r.Lumen.DiffuseIndirect.Allow": "1",
                    "r.Nanite":            "1",
                    "r.Streaming.PoolSize":"2048",
                },
            },
            "ULTRA_QUALITY": {
                "SystemSettings": {
                    "r.ShadowQuality":       "5",
                    "r.ScreenPercentage":    "100",
                    "r.Lumen.DiffuseIndirect.Allow": "1",
                    "r.RayTracing.Reflections": "1",
                    "r.Streaming.PoolSize":  "4096",
                },
            },
        },
    ),

    "REDengine4": EngineProfile(
        engine="REDengine 4 (Cyberpunk 2077)",
        config_paths=[
            "%APPDATA%\\CD Projekt Red\\Cyberpunk 2077\\UserSettings.json",
            "%USERPROFILE%\\Documents\\CD Projekt Red\\Cyberpunk 2077\\UserSettings.json",
        ],
        config_keys={
            "ULTRA_PERFORMANCE": {
                "UserSettings": {
                    "LODLevel":            "4",
                    "ResolutionScale":     "0.50",
                    "ShadowsEnabled":      "false",
                    "GlobalIlluminationType": "None",
                    "ReflectionMode":      "None",
                    "FogEnabled":          "false",
                    "DepthOfField":        "false",
                    "MotionBlur":          "false",
                    "LensFlare":           "false",
                    "ChromaticAberration": "false",
                }
            },
            "PERFORMANCE": {
                "UserSettings": {
                    "LODLevel":            "2",
                    "ResolutionScale":     "0.60",
                    "ShadowsEnabled":      "false",
                    "GlobalIlluminationType": "None",
                    "ReflectionMode":      "None",
                    "FogEnabled":          "false",
                    "MotionBlur":          "false",
                }
            },
            "BALANCED": {
                "UserSettings": {
                    "LODLevel":            "1",
                    "ResolutionScale":     "0.75",
                    "GlobalIlluminationType": "SSGI",
                    "ReflectionMode":      "SSR",
                    "MotionBlur":          "false",
                }
            },
            "QUALITY": {
                "UserSettings": {
                    "LODLevel":            "0",
                    "ResolutionScale":     "0.90",
                    "GlobalIlluminationType": "SSGI",
                    "ReflectionMode":      "RTR",
                }
            },
            "ULTRA_QUALITY": {
                "UserSettings": {
                    "LODLevel":            "0",
                    "ResolutionScale":     "1.00",
                    "GlobalIlluminationType": "PT",
                    "ReflectionMode":      "PT",
                    "RayTracingShadows":   "true",
                }
            },
        },
        notes="Path tracing requires RTX. Use ULTRA_QUALITY carefully.",
    ),

    "REDengine3": EngineProfile(
        engine="REDengine 3 (The Witcher 3)",
        config_paths=[
            "%USERPROFILE%\\Documents\\The Witcher 3\\user.settings",
        ],
        config_keys={
            "ULTRA_PERFORMANCE": {
                "Rendering": {
                    "TextureMemoryBudget":   "Low",
                    "ShadowsEnabled":        "false",
                    "FoliageVisibilityRange":"Low",
                    "ResolutionScale":       "0.5",
                    "AmbientOcclusion":      "false",
                }
            },
            "PERFORMANCE": {
                "Rendering": {
                    "TextureMemoryBudget":   "Medium",
                    "FoliageVisibilityRange":"Low",
                    "ResolutionScale":       "0.6",
                    "AmbientOcclusion":      "false",
                }
            },
            "BALANCED": {
                "Rendering": {
                    "TextureMemoryBudget":   "High",
                    "FoliageVisibilityRange":"Medium",
                    "ResolutionScale":       "0.75",
                }
            },
            "QUALITY": {
                "Rendering": {
                    "TextureMemoryBudget": "Ultra",
                    "ResolutionScale":     "0.9",
                }
            },
            "ULTRA_QUALITY": {
                "Rendering": {
                    "TextureMemoryBudget": "Ultra",
                    "ResolutionScale":     "1.0",
                    "HairWorks":           "true",
                }
            },
        },
    ),

    "Source2": EngineProfile(
        engine="Source 2 (CS2 / Dota 2)",
        config_paths=[
            "%USERPROFILE%\\AppData\\Local\\Steam\\userdata\\{steamid}\\730\\local\\cfg\\video.txt",
        ],
        config_keys={
            "ULTRA_PERFORMANCE": {
                "VideoConfig": {
                    "setting.gpu_level":          "0",
                    "setting.cpu_level":          "0",
                    "setting.shader_quality":     "0",
                    "setting.shadowmap_res":       "512",
                    "setting.fullscreen":          "1",
                }
            },
            "PERFORMANCE": {
                "VideoConfig": {
                    "setting.gpu_level":      "1",
                    "setting.cpu_level":      "1",
                    "setting.shader_quality": "1",
                    "setting.shadowmap_res":  "1024",
                }
            },
            "BALANCED": {
                "VideoConfig": {
                    "setting.gpu_level":      "2",
                    "setting.shader_quality": "2",
                    "setting.shadowmap_res":  "2048",
                }
            },
        },
        safe_to_inject=False,  # CS2 has VAC
        notes="Source 2 with VAC — config injection only, no DLL",
    ),
}

# ─────────────────────────────────────────────────────────────────────
#  Game → Engine Mapping
# ─────────────────────────────────────────────────────────────────────

GAME_PROFILES: dict[str, GameProfile] = {
    "Cyberpunk 2077":      GameProfile("Cyberpunk 2077",       "REDengine4",       ["Cyberpunk2077.exe"],      False, False),
    "The Witcher 3":       GameProfile("The Witcher 3",        "REDengine3",       ["witcher3.exe"],            False, False),
    "Red Dead 2":          GameProfile("Red Dead Redemption 2","RAGEEngine",       ["RDR2.exe"],                False, False),
    "Elden Ring":          GameProfile("Elden Ring",           "HavokCustom",      ["eldenring.exe"],           False, False),
    "GTA V":               GameProfile("GTA V",                "RAGEEngine",       ["GTA5.exe", "GTAV.exe"],    False, True),
    "Fortnite":            GameProfile("Fortnite",             "UnrealEngine5",    ["fortnite.exe"],            True,  True),
    "Counter-Strike 2":    GameProfile("Counter-Strike 2",     "Source2",          ["cs2.exe"],                 True,  True),
    "CS:GO":               GameProfile("CS:GO",                "Source2",          ["csgo.exe"],                True,  True),
    "Valorant":            GameProfile("Valorant",             "UnrealEngine4",    ["start_protected_game.exe"],True,  True),
    "Battlefield 2042":    GameProfile("Battlefield 2042",     "Frostbite3",       ["Battlefield2042.exe"],     False, True),
}


def get_engine_profile(engine_name: str) -> Optional[EngineProfile]:
    """Return engine profile by name (fuzzy match)."""
    for key, prof in ENGINE_PROFILES.items():
        if key.lower() in (engine_name or "").lower() or (engine_name or "").lower() in key.lower():
            return prof
    return None


def get_game_profile(game_name: str) -> Optional[GameProfile]:
    """Return game profile by name."""
    return GAME_PROFILES.get(game_name)


def get_config_keys_for_tier(engine_name: str, tier: str) -> dict:
    """Get all config key overrides for a quality tier."""
    profile = get_engine_profile(engine_name)
    if not profile:
        return {}
    return profile.config_keys.get(tier, {})


def list_all_games() -> list[str]:
    return list(GAME_PROFILES.keys())
