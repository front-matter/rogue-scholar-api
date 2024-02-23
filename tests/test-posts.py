"""Test posts"""
import pytest  # noqa: F401
from api.posts import (
    extract_all_posts,
    extract_all_posts_by_blog,
    upsert_single_post,
    get_urls,
    get_references,
    get_relationships,
    # get_title,
    get_summary,
)


@pytest.fixture(scope="session")
def vcr_config():
    """VCR configuration."""
    return {"filter_headers": ["apikey", "key", "X-TYPESENSE-API-KEY", "authorization"]}


@pytest.mark.asyncio
async def test_extract_all_posts():
    """Extract all posts"""
    result = await extract_all_posts()
    assert len(result) == 0
    # post = result[0]
    # assert post["title"] is not None


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_posts_by_blog_wordpressorg():
    """Extract posts by blog wordpress.org"""
    slug = "epub_fis"
    result = await extract_all_posts_by_blog(slug, page=1, update_all=True)
    assert len(result) == 50
    # post = result[0]
    # assert post["title"] == "PID Network Deutschland nimmt Fahrt auf"
    # assert post["authors"][0] == {"name": "Gastautor(en)"}
    # assert post["tags"] == [
    #     "Elektronisches Publizieren",
    #     "Forschungsinformationen &amp; Systeme",
    #     "Identitfier",
    #     "Projekt",
    #     "PID",
    # ]
    # assert post["language"] == "de"


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_posts_by_blog_wordpresscom():
    """Extract posts by blog wordpress.com"""
    slug = "wisspub"
    result = await extract_all_posts_by_blog(slug, page=1, update_all=True)
    assert len(result) == 50
    post = result[0]
    assert (
        post["title"]
        == "DOIs für Wissenschaftsblogs? – Ein Interview mit Martin Fenner zu Rogue Scholar"
    )
    assert post["authors"][0] == {
        "name": "Heinz Pampel",
        "url": "https://orcid.org/0000-0003-3334-2771",
    }
    assert post["tags"] == [
        "Langzeitarchivierung",
        "Open Science",
        "Publikationsverhalten",
        "Web 2.0",
        "Wissenschaftskommunikation",
    ]
    assert post["language"] == "de"


@pytest.mark.asyncio
async def test_extract_posts_by_archived_blog():
    """Extract posts by archived_blog"""
    slug = "thor"
    result = await extract_all_posts_by_blog(slug, page=1, update_all=True)
    assert result == []


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_posts_by_blog_ghost():
    """Extract posts by blog ghost"""
    slug = "front_matter"
    result = await extract_all_posts_by_blog(slug, page=1, update_all=True)
    assert len(result) == 50
    post = result[0]
    assert post["title"] == "commonmeta-py now supports metadata lists"
    assert post["authors"][0] == {
        "name": "Martin Fenner",
        "url": "https://orcid.org/0000-0003-1419-2405",
    }
    # assert len(post["images"]) == 0
    # assert post["images"][0] == {
    #     "alt": "",
    #     "height": "190",
    #     "sizes": "(min-width: 720px) 720px",
    #     "src": "https://blog.front-matter.io/content/images/2023/10/mermaid-figure-1.png",
    #     "srcset": "https://blog.front-matter.io/content/images/size/w600/2023/10/mermaid-figure-1.png "
    #     "600w, "
    #     "https://blog.front-matter.io/content/images/size/w1000/2023/10/mermaid-figure-1.png "
    #     "1000w, "
    #     "https://blog.front-matter.io/content/images/size/w1600/2023/10/mermaid-figure-1.png "
    #     "1600w, "
    #     "https://blog.front-matter.io/content/images/size/w2400/2023/10/mermaid-figure-1.png "
    #     "2400w",
    #     "width": "2000",
    # }
    # assert (
    #     post["image"]
    #     == "https://images.unsplash.com/flagged/photo-1552425083-0117136f7d67?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3wxMTc3M3wwfDF8c2VhcmNofDIxfHxjYW5vcHl8ZW58MHx8fHwxNjk3MDQwMDk1fDA&ixlib=rb-4.0.3&q=80&w=2000"
    # )
    assert len(post["reference"]) == 2
    assert post["reference"][0] == {
        "doi": "https://doi.org/10.53731/cp7apdj-jk5f471",
        "key": "ref1",
        "title": "Announcing Commonmeta",
        "publicationYear": "2023",
    }
    assert post["tags"] == ["News", "Rogue Scholar"]
    assert post["language"] == "en"


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_posts_by_blog_ghost_updated():
    """Extract posts by blog ghost updated only"""
    slug = "front_matter"
    result = await extract_all_posts_by_blog(slug, page=1, update_all=False)
    assert len(result) == 0


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_posts_by_blog_substack():
    """Extract posts by blog substack"""
    slug = "cwagen"
    result = await extract_all_posts_by_blog(slug, page=1, update_all=True)
    assert len(result) == 50
    post = result[0]
    assert post["title"] == "Physical Organic Chemistry: Alive or Dead?"
    assert post["authors"][0] == {
        "name": "Corin Wagen",
        "url": "https://orcid.org/0000-0003-3315-3524",
    }
    assert post["tags"] == []


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_posts_by_blog_json_feed():
    """Extract posts by blog json feed"""
    slug = "ropensci"
    result = await extract_all_posts_by_blog(slug, page=1, update_all=True)
    assert len(result) == 50
    post = result[0]
    assert post["title"] == "rOpenSci News Digest, February 2024"
    assert post["authors"][0] == {"name": "The rOpenSci Team"}
    assert post["url"] == "https://ropensci.org/blog/2024/02/23/news-february-2024"
    assert len(post["reference"]) == 0
    assert post["tags"] == ["Newsletter"]


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_posts_by_blog_json_feed_updated():
    """Extract posts by blog json feed only updated"""
    slug = "ropensci"
    result = await extract_all_posts_by_blog(slug, page=1, update_all=False)
    assert len(result) == 0


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_posts_by_blog_json_feed_with_pagination():
    """Extract posts by blog json feed with pagination"""
    slug = "ropensci"
    result = await extract_all_posts_by_blog(slug, page=2, update_all=True)
    assert len(result) == 50
    post = result[0]
    assert (
        post["title"]
        == "rOpenSci Champions Program Teams: Meet Marcos Prunello and Lukas Wallrich"
    )
    assert (
        post["url"]
        == "https://ropensci.org/blog/2023/04/18/ropensci-champions-program-teams-meet-marcos-prunello-and-lukas-wallrich"
    )
    assert post["tags"] == ["Community", "Champions Program"]


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_posts_by_blog_organizational_author():
    """Extract posts by blog organizational author"""
    slug = "leidenmadtrics"
    result = await extract_all_posts_by_blog(slug, page=1, update_all=True)
    assert len(result) == 50
    post = result[0]
    assert (
        post["title"] == "The UNESCO Open Science Outlook: OS progresses, but unequally"
    )
    assert post["authors"][0] == {
        "name": "Ismael Rafols",
        "url": "https://orcid.org/0000-0002-6527-7778",
    }


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_posts_by_blog_blogger():
    """Extract posts by blogger blog"""
    slug = "iphylo"
    result = await extract_all_posts_by_blog(slug, page=3, update_all=True)
    assert len(result) == 50
    post = result[0]
    assert post["title"] == "Notes on finding georeferenced sequences in GenBank"
    assert post["authors"][0] == {
        "name": "Roderic Page",
        "url": "https://orcid.org/0000-0002-7101-9767",
    }
    assert (
        post["url"]
        == "https://iphylo.blogspot.com/2017/10/notes-on-finding-georeferenced.html"
    )
    assert len(post["reference"]) == 0
    assert post["tags"] == ["GBIF", "Genbank", "Georeferencing", "Note To Self"]


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_posts_by_blog_atom():
    """Extract posts by blog atom"""
    slug = "eve"
    result = await extract_all_posts_by_blog(slug, page=3, update_all=True)
    assert len(result) == 50
    post = result[0]
    assert post["title"] == "OA books being reprinted under CC BY license"
    assert post["authors"][0] == {
        "name": "Martin Paul Eve",
        "url": "https://orcid.org/0000-0002-5589-8511",
    }
    assert (
        post["url"]
        == "https://eve.gd/2021/03/02/oa-books-being-reprinted-under-cc-by-license"
    )
    assert post["tags"] == []


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_posts_by_blog_rss():
    """Extract posts by blog rss"""
    slug = "tarleb"
    result = await extract_all_posts_by_blog(slug, page=1, update_all=True)
    assert len(result) == 18
    post = result[0]
    assert post["title"] == "Typst Musings"
    assert post["authors"][0] == {"name": "Albert Krewinkel"}
    assert post["tags"] == ["PDF"]


@pytest.mark.vcr
def test_upsert_single_post_in_the_future():
    """Upsert single post in the future"""
    post = {"title": "In the future", "published_at": 2000000000}
    result = upsert_single_post(post)
    assert result == {}


@pytest.mark.vcr
def test_upsert_single_post():
    """Upsert single post"""
    post = {
        "authors": [
            {
                "name": "Maëlle Salmon",
                "url": "https://orcid.org/0000-0002-2815-0399",
            },
            {
                "name": "Yanina Bellini Saibene",
                "url": "https://orcid.org/0000-0002-4522-7466",
            },
        ],
        "blog_name": "rOpenSci - open tools for open science",
        "blog_slug": "ropensci",
        "content_text": """As part of our [multilingual publishing
project](/multilingual-publishing/), and with [funding from the R
Consortium](https://www.r-consortium.org/all-projects/awarded-projects/2022-group-2),
we've worked on the R package
[babeldown](https://docs.ropensci.org/babeldown/) for translating
Markdown-based content using the DeepL API.In this tech note, we'll show
how you can use babeldown to translate a Hugo blog post!

## Motivation

Translating a Markdown blog post from your R console is not only more
comfortable (when you've already written said blog post in R), but also
less frustrating.With babeldown, compared to copy-pasting the content of
a blog post into some translation service, the Markdown syntax won't be
broken^[1](#fn:1){.footnote-ref role="doc-noteref"}^, and code chunks
won't be translated.This works, because under the hood, babeldown uses
[tinkr](https://docs.ropensci.org/tinkr) to produce XML which it then
sends to the DeepL API, flagging some tags as not to be translated. It
then converts the XML translated by DeepL back into Markdown again.

Now, as you might expect this machine-translated content isn't perfect
yet!You will still need a human or two to review and amend the
translation.Why not have the humans translate the post from scratch
then?We have observed that editing an automatic translation is faster
than translating the whole post, and that it frees up mental space for
focusing on implementing translation rules such as gender-neutral
phrasing.

## Setup

### Pre-requisites on the Hugo website

[`babeldown::deepl_translate_hugo()`](https://docs.ropensci.org/babeldown/reference/deepl_translate_hugo.html)
assumes the Hugo website uses

- leaf bundles (each post in a folder,
  `content/path-to-leaf-bundle/index.md`);
- multilingualism so that a post in (for example) Spanish lives in
  `content/path-to-leaf-bundle/index.es.md`.

babeldown could be extended work with other Hugo multilingual setups. If
you'd be interested in using babeldown with a different setup, please
open an issue in the [babeldown
repository](https://github.com/ropensci-review-tools/babeldown/)!

Note that babeldown won't be able to determine the default language of
your website^[2](#fn:2){.footnote-ref role="doc-noteref"}^ so even if
your website's default language is English, babeldown will place an
English translation in a file called ".en.md" not ".md".Hugo will
recognize the new file all the same (at least in our setup).

### DeepL pre-requisites

First check that your desired source and target languages are supported
by the DeepL API!Look up the [docs of the `source_lang` and
`target_lang` API
parameters](https://www.deepl.com/docs-api/translate-text) for a full
list.

Once you know you'll be able to take advantage of the DeepL API, you'll
need to create an account for [DeepL's translation service
API](https://www.deepl.com/en/docs-api/).Note that even getting a free
account requires registering a payment method with them.

### R pre-requisites

You'll need to install babeldown from rOpenSci R-universe:

::: {.highlight}
``` {.chroma tabindex="0"}
install.packages('babeldown', repos = c('https://ropensci.r-universe.dev', 'https://cloud.r-project.org'))
```
:::

Then, in each R session, set your DeepL API key via the environment
variable DEEPL_API_KEY. You could store it once and for all with the
[keyring](https://r-lib.github.io/keyring/index.html) package and
retrieve it in your scripts like so:

::: {.highlight}
``` {.chroma tabindex="0"}
Sys.setenv(DEEPL_API_KEY = keyring::key_get("deepl"))
```
:::

Lastly, the DeepL API URL depends on your API plan.babeldown uses the
DeepL free API URL by default.If you use a Pro plan, set the API URL in
each R session/script via

::: {.highlight}
``` {.chroma tabindex="0"}
Sys.setenv("DEEPL_API_URL" = "https://api.deepl.com")
```
:::

## Translation!

You could run the code below

::: {.highlight}
``` {.chroma tabindex="0"}
babeldown::deepl_translate_hugo(  post_path = <path-to-post>,   source_lang = "EN",  target_lang = "ES",  formality = "less" # that's how we roll here!)
```
:::

but we'd recommend a tad more work for your own good.

## Translation using a Git/GitHub workflow

If you use version control, having the translation as a diff is very
handy!

### First: In words and pictures

- In the branch of your post (let's call it "new-post") create a
  placeholder: save your original blog post (`index.es.md`) under the
  target blog post name (`index.en.md`) and commit it, then push.

<figure>
<img src="placeholder.png"
alt="Diagram with on the left the leaf folder in the new-post branch with the post in Spanish with the text &#39;Hola&#39; and an image; on the right the leaf folder in the new-post branch with the post in Spanish with the text &#39;hola&#39;, the post with the English target filename with the text &#39;hola&#39;, and the image." />
</figure>

- Create a new branch, "auto-translate" for instance.
- Run `babeldown::deepl_translate_hugo()` with `force = TRUE`.

<figure>
<img src="translate.png"
alt="Diagram with on the left the leaf folder in the auto-translate branch with the post in Spanish with the text &#39;hola&#39;, the post with the English target filename with the text &#39;hola&#39;, and the image; on the right the only thing that changed is that the content of the post with the English target filename is now &#39;hello&#39;." />
</figure>

- Commit and push the result.
- Open a PR from the **"translation-tech-note"** branch to the
  **"new-post"** branch.The only difference between the two branches is
  the automatic translation of your post. The diff for the target blog
  post will be the diff between the source and target languages! If you
  have the good habit to start a new line after each sentence / sentence
  part, it's even better.

<figure>
<img src="pr.png"
alt="Drawing of the pull request from the auto-translate to the new-post branch where the difference is that the content of the post with the English target filename has now been translated to English." />
</figure>

- The human translators can then a open a second PR to the translation
  branch with their edits! Or they can add their edits as [PR
  suggestions](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/commenting-on-a-pull-request#adding-comments-to-a-pull-request).

### Again: In code

Now let's go over this again, but with a coding workflow. Here, we'll
use fs and gert (but you do you!), and we'll assume your current
directory is the root of the website folder, and also the root of the
git repository.

- In the post branch, (again, let's call it "new-post"), save your
  original blog post (`index.es.md`) under the target blog post name
  (`index.en.md`) and commit it, then push.

::: {.highlight}
``` {.chroma tabindex="0"}
fs::file_copy(  file.path("content", "blog", "2023-10-01-r-universe-interviews", "index.es.md"),  file.path("content", "blog", "2023-10-01-r-universe-interviews", "index.en.md"))gert::git_add(file.path("content", "blog", "2023-10-01-r-universe-interviews", "index.en.md"))gert::git_commit("Add translation placeholder")gert::git_push()
```
:::

- Create a new branch, "auto-translate" for instance.

::: {.highlight}
``` {.chroma tabindex="0"}
gert::git_branch_create("translation-tech-note")
```
:::

- Run `babeldown::deepl_translate_hugo()` with `force = TRUE`.

::: {.highlight}
``` {.chroma tabindex="0"}
babeldown::deepl_translate_hugo(  post_path = file.path("content", "blog", "2023-10-01-r-universe-interviews", "index.es.md"),  force = TRUE,  yaml_fields = c("title", "description", "tags"),  source_lang = "ES",  target_lang = "EN-US")
```
:::

You can also omit the `post_path` argument if you're running the code
from RStudio IDE and if the open and focused file (the one you see above
your console) is the post to be translated.

::: {.highlight}
``` {.chroma tabindex="0"}
babeldown::deepl_translate_hugo(  force = TRUE,  yaml_fields = c("title", "description", "tags"),  source_lang = "ES",  target_lang = "EN-US")
```
:::

- Commit the result with the code below.

::: {.highlight}
``` {.chroma tabindex="0"}
gert::git_add(file.path("content", "blog", "2023-10-01-r-universe-interviews", "index.en.md"))gert::git_commit("Add translation")gert::git_push()
```
:::

- Open a PR from the **"translation-tech-note"** branch to the
  **"new-post"** branch.The only difference between the two branches is
  the automatic translation of
  `"content/blog/2023-10-01-r-universe-interviews/index.en.md"`.

- The human translators can then a open a *second* PR to the translation
  branch with their edits! Or they can add their edits as [PR
  suggestions](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/commenting-on-a-pull-request#adding-comments-to-a-pull-request).

### Summary of branches and PRs

In the end there should be two to three branches:

- branch A with blog post in Spanish and placeholder blog post for
  English (with Spanish content) -- PR to main;
- branch B with blog post automatically translated to English -- PR to
  branch A;
- Optionally branch C with blog post's English automatic translation
  edited by a human -- PR to branch B. If branch C does not exist, edits
  by a human are made as PR review suggestions in the PR from B to A.

The PR are merged in this order:

- PR to branch B;
- PR to branch A;
- PR to main.

### Real example

- [PR adding a post to the rOpenSci
  blog](https://github.com/ropensci/roweb3/pull/629), notice it's a PR
  from the **"r-universe-interviews"** branch to the **"main"
  (default)** branch;
- [PR adding the automatic
  translation](https://github.com/ropensci/roweb3/pull/639), notice it's
  a PR to the **"r-universe-interviews"** branch.

<figure>
<img src="pr-diff.png"
alt="Screenshot of the files tab of the pull request adding the automatic translation, where we observe Spanish text in the YAML metadata and Markdown content has been translated to English." />
</figure>

Yanina tweaked the automatic translation by suggesting changes on the
PR, then accepting them.

<figure>
<img src="pr-comments.png"
alt="Screenshot of the main tab of the pull request adding the automatic translation, where we observe a comment by Yanina replacing the word &#39;article&#39; with &#39;blog post&#39; and fixing the name of &#39;R-universe&#39;." />
</figure>

### YAML fields

By default babeldown translates the YAML fields "title" and
"description".If you have text in more of them, use the `yaml_fields`
argument of `babeldown::deepl_translate_hugo()`.

Note that if babeldown translates the title, it updates the slug.

### Glossary

Imagine you have a few preferences for some words -- something you'll
build up over time.

::: {.highlight}
``` {.chroma tabindex="0"}
readr::read_csv(  system.file("example-es-en.csv", package = "babeldown"),   show_col_types = FALSE)
```
:::

``` {tabindex="0"}
## # A tibble: 2 × 2##   Spanish     English   ##   <chr>       <chr>     ## 1 paquete     package   ## 2 repositorio repository
```

You can record these preferred translations in a glossary in your DeepL
account

::: {.highlight}
``` {.chroma tabindex="0"}
deepl_upsert_glossary(  <path-to-csv-file>,  glossary_name = "rstats-glosario",  target_lang = "Spanish",  source_lang = "English")
```
:::

You'd use the exact same code to *update* the glossary hence the name
"upsert" for the function.You need one glossary per source language /
target language pair: the English-Spanish glossary can't be used for
Spanish to English for instance.

In your `babeldown::deepl_translate_hugo()` call you then use the
glossary name (here "rstats-glosario") for the `glossary` argument.

### Formality

`deepl_translate_hugo()` has a `formality` argument.Now, the DeepL API
only supports this for some languages as explained in the [documentation
of the `formality` API
parameter](https://www.deepl.com/docs-api/translate-text):

> Sets whether the translated text should lean towards formal or
> informal language. This feature currently only works for target
> languages DE (German), FR (French), IT (Italian), ES (Spanish), NL
> (Dutch), PL (Polish), PT-BR and PT-PT (Portuguese), JA (Japanese), and
> RU (Russian). (...) Setting this parameter with a target language that
> does not support formality will fail, unless one of the prefer\_...
> options are used.

Therefore to be sure a translation will work, instead of writing
`formality = "less"` you can write `formality = "prefer_less"` which
will only use formality if available.

## Conclusion

In this post we explained how to translate a Hugo blog post using
babeldown.Although the gist is to use one call to
`babeldown::deepl_translate_hugo()`,

- one needs to indicate the API URL and key,
- one can improve results by using the function's different arguments,
- we recommend pairing the translation with a Git + GitHub (or GitLab,
  gitea...) workflow.

babeldown has
[functions](https://docs.ropensci.org/babeldown/reference/index.html)
for translating Quarto book chapters, any Markdown file, and any
Markdown string, with similar arguments and recommended usage, so
explore its reference!

We'd be happy to hear about your [use cases](/usecases/).

::: {.footnotes role="doc-endnotes"}

------------------------------------------------------------------------

1.  ::: {#fn:1}
    But you should refer to [tinkr
    docs](https://docs.ropensci.org/tinkr/#loss-of-markdown-style) to
    see what might change in the Markdown syntax
    style. [↩︎](#fnref:1){.footnote-backref role="doc-backlink"}
    :::

2.  ::: {#fn:2}
    adding code to handle Hugo's ["bewildering array of possible config
    locations"](https://github.com/r-lib/hugodown/issues/14#issuecomment-632850506)
    and two possible formats (YAML and TOML) is out of scope for
    babeldown at this point. [↩︎](#fnref:2){.footnote-backref
    role="doc-backlink"}
    :::
:::
""",
        "summary": '<p>As part of our <a href="/multilingual-publishing/">multilingual publishing project</a>, and with <a href="https://www.r-consortium.org/all-projects/awarded-projects/2022-group-2">funding from the R Consortium</a>, we&rsquo;ve worked on the R package <a href="https://docs.ropensci.org/babeldown/">babeldown</a> for translating Markdown-based content using the DeepL API.In this tech note, we&rsquo;ll show how you can use babeldown to translate a Hugo blog post!',
        "published_at": 1695686400,
        "updated_at": 1695713432,
        "image": "placeholder.png",
        "images": [
            {
                "src": "placeholder.png",
                "alt": "Diagram with on the left the leaf folder in the new-post branch with the post in Spanish with the text 'Hola' and an image; on the right the leaf folder in the new-post branch with the post in Spanish with the text 'hola', the post with the English target filename with the text 'hola', and the image.",
            },
            {
                "src": "translate.png",
                "alt": "Diagram with on the left the leaf folder in the auto-translate branch with the post in Spanish with the text 'hola', the post with the English target filename with the text 'hola', and the image; on the right the only thing that changed is that the content of the post with the English target filename is now 'hello'.",
            },
            {
                "src": "pr.png",
                "alt": "Drawing of the pull request from the auto-translate to the new-post branch where the difference is that the content of the post with the English target filename has now been translated to English.",
            },
            {
                "src": "pr-diff.png",
                "alt": "Screenshot of the files tab of the pull request adding the automatic translation, where we observe Spanish text in the YAML metadata and Markdown content has been translated to English.",
            },
            {
                "src": "pr-comments.png",
                "alt": "Screenshot of the main tab of the pull request adding the automatic translation, where we observe a comment by Yanina replacing the word 'article' with 'blog post' and fixing the name of 'R-universe'.",
            },
        ],
        "language": "en",
        "reference": [],
        "relationships": [],
        "tags": ["Tech Notes", "Multilingual"],
        "title": "How to Translate a Hugo Blog Post with Babeldown",
        "url": "https://ropensci.org/blog/2023/09/26/how-to-translate-a-hugo-blog-post-with-babeldown",
        "guid": "https://ropensci.org/blog/2023/09/26/how-to-translate-a-hugo-blog-post-with-babeldown/",
    }
    result = upsert_single_post(post)
    assert result["title"] == "How to Translate a Hugo Blog Post with Babeldown"
    assert result["doi"] == "https://doi.org/10.59350/evaf9-2qf48"


def test_get_urls():
    """Get urls"""
    html = "Bla bla <a href='https://iphylo.blogspot.com/feeds/posts/default?start-index=1&max-results=50'>."
    result = get_urls(html)
    assert result == [
        "https://iphylo.blogspot.com/feeds/posts/default?start-index=1&max-results=50"
    ]


def test_get_references():
    """Extract references"""
    html = """Bla. <h2>References</h2><p>Fenner, M. (2023). <em>Rogue Scholar has an API</em>. 
    <a href="https://doi.org/10.53731/ar11b-5ea39">https://doi.org/10.53731/ar11b-5ea39</a></p>
    <p>Crossref, Hendricks, G., Center for Scientific Integrity, &amp; Lammey, R. (2023). 
    <em>Crossref acquires Retraction Watch data and opens it for the scientific community</em>. 
    <a href="https://doi.org/10.13003/c23rw1d9">https://doi.org/10.13003/c23rw1d9</a></p>"""

    result = get_references(html)
    assert len(result) == 2
    assert result[0] == {
        "key": "ref1",
        "doi": "https://doi.org/10.53731/ar11b-5ea39",
        "title": "Rogue Scholar has an API",
        "publicationYear": "2023",
    }


def test_get_relationships():
    """Extract relationships"""
    html = """Bla. <h2>Acknowledgments</h2><p>This blog post was originally published on the <a href="https://doi.org/10.5438/3dfw-z4kq">DataCite Blog</a>.</p>"""

    result = get_relationships(html)
    assert len(result) == 1
    assert result[0] == {
        "url": "https://doi.org/10.5438/3dfw-z4kq",
        "type": "IsIdenticalTo",
    }


def test_get_relationships_funding():
    """Extract funding relationships"""
    html = """Bla. <h2>Acknowledgments</h2><p>This work was funded by the European Union’s Horizon 2020 research and innovation programme under <a href="https://doi.org/10.3030/654039">grant agreement No. 654039</a>.</p>"""

    result = get_relationships(html)
    assert len(result) == 1
    assert result[0] == {
        "url": "https://doi.org/10.3030/654039",
        "type": "HasAward",
    }


# def test_get_title():
#     """Sanitize title with spaces."""
#     title = "  <h2>Bla</h2/><i>bla</i>"
#     result = get_title(title)
#     assert result == "<strong>Bla</strong><i>bla</i>"


def test_get_summary():
    """Sanitize and truncate summary."""
    summary = """
    There’s something special about language. It is ‘our own’, it is ‘us’, in a profound way, and quite surprisingly, more so than art. I was deeply struck by this when I first saw reactions to large generative language models that created realistic, human-ish prose. Notably, those mature enough to reach a non-professional audience – ChatGPT based on GPT-3 and later GPT-4 – came quite some time after models that could create fairly acceptable visual ‘art’.1 The appearance of synthetic language-like products (SLLPs), as I like to call the output of such generative models, came well after the appearance of synthetic simulacra of visual art,2 yet elicited much less fervent responses."""
    result = get_summary(summary)
    assert len(result) <= 450
    assert result.endswith("human-ish prose.")
