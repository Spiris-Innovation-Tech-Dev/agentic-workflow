use ratatui::style::{Color, Modifier, Style};

/// Crew color scheme, matching state_tools.py CREW_COLOR_SCHEMES.
#[allow(dead_code)]
pub struct CrewColorScheme {
    pub name: &'static str,
    pub tab: Color,
    pub bg: Color,
    pub fg: Color,
}

pub const CREW_COLOR_SCHEMES: &[CrewColorScheme] = &[
    CrewColorScheme {
        name: "Crew Ocean",
        tab: Color::Rgb(0x1A, 0x6B, 0x8A),
        bg: Color::Rgb(0x0C, 0x1B, 0x2A),
        fg: Color::Rgb(0xC8, 0xD6, 0xE5),
    },
    CrewColorScheme {
        name: "Crew Forest",
        tab: Color::Rgb(0x2D, 0x7D, 0x46),
        bg: Color::Rgb(0x0E, 0x1F, 0x14),
        fg: Color::Rgb(0xC5, 0xD1, 0xC0),
    },
    CrewColorScheme {
        name: "Crew Sunset",
        tab: Color::Rgb(0xC7, 0x5B, 0x39),
        bg: Color::Rgb(0x1F, 0x12, 0x0E),
        fg: Color::Rgb(0xD8, 0xC8, 0xBA),
    },
    CrewColorScheme {
        name: "Crew Amethyst",
        tab: Color::Rgb(0x7B, 0x5E, 0xA7),
        bg: Color::Rgb(0x16, 0x12, 0x1F),
        fg: Color::Rgb(0xCC, 0xC4, 0xD8),
    },
    CrewColorScheme {
        name: "Crew Steel",
        tab: Color::Rgb(0x5C, 0x7A, 0x8A),
        bg: Color::Rgb(0x14, 0x1C, 0x22),
        fg: Color::Rgb(0xC0, 0xCC, 0xD4),
    },
    CrewColorScheme {
        name: "Crew Ember",
        tab: Color::Rgb(0xB8, 0x5C, 0x3A),
        bg: Color::Rgb(0x1A, 0x11, 0x0D),
        fg: Color::Rgb(0xD4, 0xC4, 0xB4),
    },
    CrewColorScheme {
        name: "Crew Frost",
        tab: Color::Rgb(0x4B, 0xA3, 0xC7),
        bg: Color::Rgb(0x0D, 0x18, 0x20),
        fg: Color::Rgb(0xC4, 0xD4, 0xE0),
    },
    CrewColorScheme {
        name: "Crew Earth",
        tab: Color::Rgb(0x8D, 0x7B, 0x4A),
        bg: Color::Rgb(0x1A, 0x17, 0x0E),
        fg: Color::Rgb(0xD0, 0xC8, 0xB8),
    },
];

/// Get color scheme by index (wraps around).
pub fn get_scheme(index: usize) -> &'static CrewColorScheme {
    &CREW_COLOR_SCHEMES[index % CREW_COLOR_SCHEMES.len()]
}

/// Get color scheme by name, falling back to index 0.
#[allow(dead_code)]
pub fn get_scheme_by_name(name: &str) -> &'static CrewColorScheme {
    CREW_COLOR_SCHEMES
        .iter()
        .find(|s| s.name == name)
        .unwrap_or(&CREW_COLOR_SCHEMES[0])
}

pub fn header_style() -> Style {
    Style::default()
        .fg(Color::Cyan)
        .add_modifier(Modifier::BOLD)
}

pub fn selected_style() -> Style {
    Style::default()
        .bg(Color::DarkGray)
        .add_modifier(Modifier::BOLD)
}

pub fn dim_style() -> Style {
    Style::default().fg(Color::DarkGray)
}

pub fn phase_style(_phase: &str, is_current: bool, is_completed: bool) -> Style {
    if is_completed {
        Style::default().fg(Color::Green)
    } else if is_current {
        Style::default()
            .fg(Color::Yellow)
            .add_modifier(Modifier::BOLD)
    } else {
        Style::default().fg(Color::DarkGray)
    }
}
