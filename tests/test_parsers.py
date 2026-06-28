from bls_login_automation.parsers.captcha import extract_visible_captcha_image_ids


def test_extract_visible_captcha_image_ids_uses_top_z_index_per_cell():
    html = """
    <html><head><style>
      .a { position:absolute; left:0px; top:0px; z-index:1; }
      .b { position:absolute; left:0px; top:0px; z-index:5; }
      .c { position:absolute; left:110px; top:0px; z-index:2; }
      .hide { display:none; }
    </style></head><body>
      <div class="a" id="old"><img class="captcha-img" onclick="Select('old',this)"></div>
      <div class="b" id="new"><img class="captcha-img" onclick="Select('new',this)"></div>
      <div class="c" id="other"><img class="captcha-img" onclick="Select('other',this)"></div>
      <div class="hide" id="hidden"><img class="captcha-img" onclick="Select('hidden',this)"></div>
    </body></html>
    """
    assert extract_visible_captcha_image_ids(html) == ["new", "other"]
