on run argv
  if (count of argv) < 1 then
    error "Usage: osascript create_character_brief.applescript <brief-title> [output.docx]"
  end if

  set briefTitle to item 1 of argv
  set outPath to my resolveOutputPath(argv, briefTitle)
  set templateText to my buildCharacterTemplate(briefTitle)

  do shell script "/bin/rm -f " & quoted form of outPath

  with timeout of 600 seconds
    tell application "Pages"
      launch
      set d to make new document
      delay 0.4
      set body text of d to templateText
      delay 0.2
      my applyStandardFormatting(d)
      export d to POSIX file outPath as Microsoft Word
      close d saving no
    end tell
  end timeout
end run

on resolveOutputPath(argv, briefTitle)
  if (count of argv) >= 2 then
    set rawOutPath to POSIX path of (POSIX file (item 2 of argv))
  else
    set cwdPath to do shell script "/bin/pwd"
    if cwdPath does not end with "/" then set cwdPath to cwdPath & "/"
    set rawOutPath to cwdPath & my safeFilename(briefTitle) & ".docx"
  end if

  if rawOutPath does not end with ".docx" then set rawOutPath to rawOutPath & ".docx"
  return rawOutPath
end resolveOutputPath

on buildCharacterTemplate(briefTitle)
  set nl to return

  set lineItems to {"Character Brief: " & briefTitle, ¬
    "Name: [Character Name]", ¬
    "Age: [Age]", ¬
    "Career: [Career]", ¬
    "Hometown: [Hometown]", ¬
    "Education: [Education]", ¬
    "Backstory", ¬
    "Write this section in first person. Use multiple short paragraphs like the existing briefs.", ¬
    "", ¬
    "Explain the character's history, status, secrets, and why they are here tonight.", ¬
    "", ¬
    "Objective", ¬
    "State the character's goal for the evening in 1-3 sentences.", ¬
    "Connections", ¬
    "Connection 1, [Name] (<played by>)", ¬
    "", ¬
    "Connection 2, [Name] (<played by>)", ¬
    "", ¬
    "Connection 3, [Name] (<played by>)"}

  set AppleScript's text item delimiters to nl
  set outText to lineItems as text
  set AppleScript's text item delimiters to ""
  return outText
end buildCharacterTemplate

on safeFilename(s)
  set t to s as text
  set t to my replaceText(t, "/", "-")
  set t to my replaceText(t, ":", " -")
  set t to my replaceText(t, return, " ")
  set t to my replaceText(t, linefeed, " ")
  set t to my replaceText(t, tab, " ")
  return t
end safeFilename

on replaceText(sourceText, findText, replaceWith)
  set AppleScript's text item delimiters to findText
  set parts to text items of sourceText
  set AppleScript's text item delimiters to replaceWith
  set outText to parts as text
  set AppleScript's text item delimiters to ""
  return outText
end replaceText

on applyStandardFormatting(d)
  tell application "Pages"
    try
      set font of body text of d to "Times New Roman"
    on error
      set font of body text of d to "TimesNewRomanPSMT"
    end try
    set size of body text of d to 12
    set color of body text of d to {0, 0, 0}

    set pCount to count of paragraphs of body text of d

    repeat with i from 1 to pCount
      set pTextTrim to my trimText(paragraph i of body text of d as text)
      if pTextTrim is not "" then
        my styleParagraph(d, i, 16, true)
        exit repeat
      end if
    end repeat

    repeat with i from 1 to pCount
      set pTextTrim to my trimText(paragraph i of body text of d as text)
      ignoring case
        if pTextTrim is "backstory" or pTextTrim is "objective" or pTextTrim is "connections" or pTextTrim is "overview" then
          my styleParagraph(d, i, 13, true)
        else if pTextTrim starts with "name:" or pTextTrim starts with "age:" or pTextTrim starts with "career:" or pTextTrim starts with "hometown:" or pTextTrim starts with "education:" then
          my styleParagraph(d, i, 12, true)
        end if
      end ignoring
    end repeat
  end tell
end applyStandardFormatting

on styleParagraph(d, idx, pSize, makeBold)
  tell application "Pages"
    if makeBold then
      try
        set font of paragraph idx of body text of d to "Times New Roman Bold"
      on error
        try
          set font of paragraph idx of body text of d to "TimesNewRomanPS-BoldMT"
        on error
          set font of paragraph idx of body text of d to "Times New Roman"
        end try
      end try
    else
      try
        set font of paragraph idx of body text of d to "Times New Roman"
      on error
        set font of paragraph idx of body text of d to "TimesNewRomanPSMT"
      end try
    end if
    set size of paragraph idx of body text of d to pSize
    set color of paragraph idx of body text of d to {0, 0, 0}
  end tell
end styleParagraph

on trimText(t)
  set s to t as text
  set ws to {space, return, linefeed, tab, character id 8232, character id 8233}

  repeat while s is not ""
    if (character 1 of s) is in ws then
      if (length of s) is 1 then return ""
      set s to text 2 thru -1 of s
    else
      exit repeat
    end if
  end repeat

  repeat while s is not ""
    if (character -1 of s) is in ws then
      if (length of s) is 1 then return ""
      set s to text 1 thru -2 of s
    else
      exit repeat
    end if
  end repeat

  return s
end trimText
