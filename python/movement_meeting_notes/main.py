"""Format markdown meeting notes for Zulip post.

A quick scrip to format meeting notes for Zulip.
The script reads a markdown file with the meeting notes and outputs
another markdown file formatted for Zulip.

To use the script, run the following command from the `movement_meeting_notes` directory:
```bash
python main.py
```

By default, the script will expect the input and output files to be in the same directory as the script,
and be named `input.md` and `output.md` respectively.

This can be changed with the ```--input``` and ```--output``` flags.
See the help message for more information:
```bash
python main.py --help
```

The input meeting notes are expected to have the following sections
(none of them is mandatory, they are just treated differently):
 * _Present_,
 * _Agenda_,
 * _Meeting notes_ and
 * _Actions_.

Sections under _Meeting notes_ are placed in spoiler blocks. Any nested bullet points are formatted to show correctly on Zulip.

Some things to note before posting:
- The text under _Present_ prefixes names with a handle - we currently need to check manually these match to Zulip usernames.
- Recently when I paste the content of "output.md" to Zulip, the whole thing is pasted within a 4-quote block.
To make it render nicely, remember to remove those 4-quotes from the first and last line of the message.
"""

import argparse
import re


def format_present_section(content):
    """Format the 'Present' section to add @** around the names."""
    pattern = re.compile(r"- (.*)")
    return pattern.sub(r"- @**\1**", content.strip())


def format_agenda_section(content):
    """Format the agenda section."""
    return format_bullet_points(content)


def format_meeting_notes_section(content):
    """Format the meeting notes to wrap sections in spoiler blocks
    and ensure correct indentation for bullet points."""
    # Split sections based on bullet point lines starting with '-'
    sections = re.split(r"\n(?=- )", content)
    formatted_sections = []

    for section in sections:
        # Extract the title of the section (first line after a dash and space)
        match = re.match(r"- (.*?)\n", section)
        if match:
            # Get spoiler header and footer
            title = match.group(1)
            spoiler_header = f"```spoiler {title}\n"
            spoiler_footer = "\n```"

            # Format bullet points in the section
            body = section.removeprefix(f"- {title}\n")
            formatted_body = format_bullet_points(body)

            # Add the spoiler block around the formatted body
            formatted_section = spoiler_header + formatted_body + spoiler_footer
            formatted_sections.append(formatted_section)
        else:
            formatted_sections.append(section)  # In case there's no match

    return "\n\n".join(formatted_sections)


def format_bullet_points(content):
    """Ensure bullet points are indented properly with 2 spaces per level."""
    lines = content.splitlines()
    formatted_lines = []

    # Make the outermost level of bullet points flush with the left margin
    min_n_spaces = min(
        [len(line) - len(line.lstrip()) for line in lines if line.strip()]
    )
    if min_n_spaces > 0:
        # remove the leading spaces from each line
        lines = [line[min_n_spaces:] for line in lines]

    # Adjust indent level based on bullet point depth
    # (change a single tab from 4 spaces to 2 spaces)
    for line in lines:
        stripped_line = line.lstrip()

        if stripped_line.startswith("- "):
            # Count leading spaces or tabs to determine the indent level
            # initial indentation is 4 spaces per level
            indent_level = (len(line) - len(stripped_line)) // 4
            # Adjust the indentation to 2 spaces per level
            formatted_lines.append("  " * indent_level + stripped_line)
        else:
            formatted_lines.append(line)

    return "\n".join(formatted_lines)


def main():
    # Set up command-line argument parser
    parser = argparse.ArgumentParser(
        description=(
            "Format a markdown file with specific indentation and spoiler blocks."
        )
    )
    parser.add_argument(
        "--input",
        type=str,
        default="input.md",
        help=(
            "Path to the input markdown file. By default, an 'input.md' file under the current directory."
        ),
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output.md",
        help=(
            "Path to the output markdown file. By default, an 'output.md' file under the current directory."
        ),
    )
    args = parser.parse_args()

    # Read input markdown
    with open(args.input, "r") as file:
        content = file.read()

    # Split the content by sections (Present, Agenda, Meeting notes, Actions)
    header_regex = (
        r"(^Actions$|#{2,} .*)"
        # split if line has Actions or #x(2 or more) heading
    )
    sections = re.split(header_regex, content, flags=re.MULTILINE)
    output = []

    for i, section in enumerate(sections):
        if bool(re.match(r"^## \d{4}-\d{2}-\d{2}.*$", section.strip())):
            output.append(section)
            output.append("\n\n")
        elif "### Present" in section:
            output.append(sections[i])
            output.append(format_present_section(sections[i + 1]))
            output.append("\n")
        elif "### Agenda" in section:
            output.append(sections[i])
            output.append(format_agenda_section(sections[i + 1]))
        elif "### Meeting notes" in section:
            output.append(sections[i])
            output.append(format_meeting_notes_section(sections[i + 1]))
        elif "Action" in section:
            # Just append Actions section as it is
            output.append(sections[i])
            output.append(sections[i + 1])

    # Write formatted content to output.md
    with open(args.output, "w") as file:
        file.write("\n".join(output))


if __name__ == "__main__":
    main()
