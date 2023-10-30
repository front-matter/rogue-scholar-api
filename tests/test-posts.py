"""Test posts"""
import pytest  # noqa: F401
from datetime import datetime
from rogue_scholar_api.posts import (
    extract_all_posts,
    extract_all_posts_by_blog,
    upsert_single_post,
    get_urls,
    get_references,
    # get_title,
    get_abstract,
)


@pytest.fixture(scope="session")
def vcr_config():
    """VCR configuration."""
    return {"filter_headers": ["apikey", "key", "X-TYPESENSE-API-KEY", "authorization"]}


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_all_posts():
    """Extract all posts"""
    result = await extract_all_posts()
    assert len(result) == 3
    post = result[0]
    assert post["title"] == "The Open Access Week in the Scholarly Blogosphere"
    assert post["authors"][0] == {
        "name": "Heinz Pampel",
        "url": "https://orcid.org/0000-0003-3334-2771",
    }
    assert post["tags"] == ['Special Issue']


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_posts_by_blog_wordpressorg():
    """Extract posts by blog wordpress.org"""
    slug = "epub_fis"
    result = await extract_all_posts_by_blog(slug, page=1, update_all=True)
    assert len(result) == 50
    post = result[0]
    assert post["title"] == "Aktualisierte OpenAIRE Richtlinie für FIS-Manager"
    assert post["authors"][0] == {"name": "Gastautor(en)"}
    assert post["tags"] == [
        "Elektronisches Publizieren",
        "Forschungsinformationssysteme",
        "Projekt",
        "OpenAIRE",
    ]


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


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_posts_by_blog_ghost():
    """Extract posts by blog ghost"""
    slug = "front_matter"
    result = await extract_all_posts_by_blog(slug, page=1, update_all=True)
    assert len(result) == 50
    post = result[0]
    assert post["title"] == "Generating Overlay blog posts"
    assert post["authors"][0] == {
        "name": "Martin Fenner",
        "url": "https://orcid.org/0000-0003-1419-2405",
    }
    assert len(post["images"]) == 1
    assert post["images"][0] == {
        "alt": "",
        "height": "190",
        "sizes": "(min-width: 720px) 720px",
        "src": "https://blog.front-matter.io/content/images/2023/10/mermaid-figure-1.png",
        "srcset": "https://blog.front-matter.io/content/images/size/w600/2023/10/mermaid-figure-1.png "
        "600w, "
        "https://blog.front-matter.io/content/images/size/w1000/2023/10/mermaid-figure-1.png "
        "1000w, "
        "https://blog.front-matter.io/content/images/size/w1600/2023/10/mermaid-figure-1.png "
        "1600w, "
        "https://blog.front-matter.io/content/images/size/w2400/2023/10/mermaid-figure-1.png "
        "2400w",
        "width": "2000",
    }
    assert (
        post["image"]
        == "https://images.unsplash.com/flagged/photo-1552425083-0117136f7d67?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3wxMTc3M3wwfDF8c2VhcmNofDIxfHxjYW5vcHl8ZW58MHx8fHwxNjk3MDQwMDk1fDA&ixlib=rb-4.0.3&q=80&w=2000"
    )
    assert len(post["reference"]) == 3
    assert post["reference"][0] == {
        "doi": "https://doi.org/10.53731/ar11b-5ea39",
        "key": "ref1",
    }
    assert post["tags"] == ["Feature"]


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
    assert post["title"] == "Organic Chemistry’s Wish List, Four Years Later"
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
    assert post["title"] == "rOpenSci News Digest, October 2023"
    assert post["authors"][0] == {
        "name": "The rOpenSci Team",
    }
    assert post["url"] == "https://ropensci.org/blog/2023/10/20/news-october-2023"
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
    assert post["title"] == "rOpenSci News Digest, December 2022"
    assert (
        post["url"]
        == "https://ropensci.org/blog/2022/12/16/ropensci-news-digest-december-2022"
    )
    assert post["tags"] == ["Newsletter"]


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_posts_by_blog_blogger():
    """Extract posts by blogger blog"""
    slug = "iphylo"
    result = await extract_all_posts_by_blog(slug, page=3, update_all=True)
    assert len(result) == 50
    post = result[0]
    assert post["title"] == "TDWG 2017: thoughts on day 1"
    assert post["authors"][0] == {
        "name": "Roderic Page",
        "url": "https://orcid.org/0000-0002-7101-9767",
    }
    assert (
        post["url"]
        == "https://iphylo.blogspot.com/2017/10/tdwg-2017-thoughts-on-day-1.html"
    )
    assert len(post["reference"]) == 0
    assert post["tags"] == ["BHL", "GBIF", "Knowledge Graph", "Linked Data", "TDWG"]


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_posts_by_blog_atom():
    """Extract posts by blog atom"""
    slug = "eve"
    result = await extract_all_posts_by_blog(slug, page=3, update_all=True)
    assert len(result) == 50
    post = result[0]
    assert (
        post["title"]
        == "The Publisher's Association's impact assessment on OA is pretty much as you'd expect"
    )
    assert post["authors"][0] == {
        "name": "Martin Paul Eve",
        "url": "https://orcid.org/0000-0002-5589-8511",
    }
    assert (
        post["url"]
        == "https://eve.gd/2021/02/17/the-publishers-associations-impact-assessment-on-oa"
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
        "blog_id": "e22ws68",
        "blog_name": "rOpenSci - open tools for open science",
        "blog_slug": "ropensci",
        "content_html": '<p>As part of our <a href="/multilingual-publishing/">multilingual publishing project</a>, and with <a href="https://www.r-consortium.org/all-projects/awarded-projects/2022-group-2">funding from the R Consortium</a>, we&rsquo;ve worked on the R package <a href="https://docs.ropensci.org/babeldown/">babeldown</a> for translating Markdown-based content using the DeepL API.In this tech note, we&rsquo;ll show how you can use babeldown to translate a Hugo blog post!</p><h2 id="motivation">Motivation</h2><p>Translating a Markdown blog post from your R console is not only more comfortable (when you&rsquo;ve already written said blog post in R), but also less frustrating.With babeldown, compared to copy-pasting the content of a blog post into some translation service, the Markdown syntax won&rsquo;t be broken<sup id="fnref:1"><a href="#fn:1" class="footnote-ref" role="doc-noteref">1</a></sup>, and code chunks won&rsquo;t be translated.This works, because under the hood, babeldown uses <a href="https://docs.ropensci.org/tinkr">tinkr</a> to produce XML which it then sends to the DeepL API, flagging some tags as not to be translated. It then converts the XML translated by DeepL back into Markdown again.</p><p>Now, as you might expect this machine-translated content isn&rsquo;t perfect yet!You will still need a human or two to review and amend the translation.Why not have the humans translate the post from scratch then?We have observed that editing an automatic translation is faster than translating the whole post, and that it frees up mental space for focusing on implementing translation rules such as gender-neutral phrasing.</p><h2 id="setup">Setup</h2><h3 id="pre-requisites-on-the-hugo-website">Pre-requisites on the Hugo website</h3><p><a href="https://docs.ropensci.org/babeldown/reference/deepl_translate_hugo.html"><code>babeldown::deepl_translate_hugo()</code></a> assumes the Hugo website uses</p><ul><li>leaf bundles (each post in a folder, <code>content/path-to-leaf-bundle/index.md</code>);</li><li>multilingualism so that a post in (for example) Spanish lives in <code>content/path-to-leaf-bundle/index.es.md</code>.</li></ul><p>babeldown could be extended work with other Hugo multilingual setups. If you&rsquo;d be interested in using babeldown with a different setup, please open an issue in the <a href="https://github.com/ropensci-review-tools/babeldown/">babeldown repository</a>!</p><p>Note that babeldown won&rsquo;t be able to determine the default language of your website<sup id="fnref:2"><a href="#fn:2" class="footnote-ref" role="doc-noteref">2</a></sup> so even if your website&rsquo;s default language is English, babeldown will place an English translation in a file called &ldquo;.en.md&rdquo; not &ldquo;.md&rdquo;.Hugo will recognize the new file all the same (at least in our setup).</p><h3 id="deepl-pre-requisites">DeepL pre-requisites</h3><p>First check that your desired source and target languages are supported by the DeepL API!Look up the <a href="https://www.deepl.com/docs-api/translate-text">docs of the <code>source_lang</code> and <code>target_lang</code> API parameters</a> for a full list.</p><p>Once you know you&rsquo;ll be able to take advantage of the DeepL API, you&rsquo;ll need to create an account for <a href="https://www.deepl.com/en/docs-api/">DeepL&rsquo;s translation service API</a>.Note that even getting a free account requires registering a payment method with them.</p><h3 id="r-pre-requisites">R pre-requisites</h3><p>You&rsquo;ll need to install babeldown from rOpenSci R-universe:</p><div class="highlight"><pre tabindex="0" class="chroma"><code class="language-r" data-lang="r"><span class="line"><span class="cl"><span class="nf">install.packages</span><span class="p">(</span><span class="s">&#39;babeldown&#39;</span><span class="p">,</span> <span class="n">repos</span> <span class="o">=</span> <span class="nf">c</span><span class="p">(</span><span class="s">&#39;https://ropensci.r-universe.dev&#39;</span><span class="p">,</span> <span class="s">&#39;https://cloud.r-project.org&#39;</span><span class="p">))</span></span></span></code></pre></div><p>Then, in each R session, set your DeepL API key via the environment variable DEEPL_API_KEY. You could store it once and for all with the <a href="https://r-lib.github.io/keyring/index.html">keyring</a> package and retrieve it in your scripts like so:</p><div class="highlight"><pre tabindex="0" class="chroma"><code class="language-r" data-lang="r"><span class="line"><span class="cl"><span class="nf">Sys.setenv</span><span class="p">(</span><span class="n">DEEPL_API_KEY</span> <span class="o">=</span> <span class="n">keyring</span><span class="o">::</span><span class="nf">key_get</span><span class="p">(</span><span class="s">&#34;deepl&#34;</span><span class="p">))</span></span></span></code></pre></div><p>Lastly, the DeepL API URL depends on your API plan.babeldown uses the DeepL free API URL by default.If you use a Pro plan, set the API URL in each R session/script via</p><div class="highlight"><pre tabindex="0" class="chroma"><code class="language-r" data-lang="r"><span class="line"><span class="cl"><span class="nf">Sys.setenv</span><span class="p">(</span><span class="s">&#34;DEEPL_API_URL&#34;</span> <span class="o">=</span> <span class="s">&#34;https://api.deepl.com&#34;</span><span class="p">)</span></span></span></code></pre></div><h2 id="translation">Translation!</h2><p>You could run the code below</p><div class="highlight"><pre tabindex="0" class="chroma"><code class="language-r" data-lang="r"><span class="line"><span class="cl"><span class="n">babeldown</span><span class="o">::</span><span class="nf">deepl_translate_hugo</span><span class="p">(</span></span></span><span class="line"><span class="cl">  <span class="n">post_path</span> <span class="o">=</span> <span class="o">&lt;</span><span class="n">path</span><span class="o">-</span><span class="n">to</span><span class="o">-</span><span class="n">post</span><span class="o">&gt;</span><span class="p">,</span> </span></span><span class="line"><span class="cl">  <span class="n">source_lang</span> <span class="o">=</span> <span class="s">&#34;EN&#34;</span><span class="p">,</span></span></span><span class="line"><span class="cl">  <span class="n">target_lang</span> <span class="o">=</span> <span class="s">&#34;ES&#34;</span><span class="p">,</span></span></span><span class="line"><span class="cl">  <span class="n">formality</span> <span class="o">=</span> <span class="s">&#34;less&#34;</span> <span class="c1"># that&#39;s how we roll here!</span></span></span><span class="line"><span class="cl"><span class="p">)</span></span></span></code></pre></div><p>but we&rsquo;d recommend a tad more work for your own good.</p><h2 id="translation-using-a-gitgithub-workflow">Translation using a Git/GitHub workflow</h2><p>If you use version control, having the translation as a diff is very handy!</p><h3 id="first-in-words-and-pictures">First: In words and pictures</h3><ul><li>In the branch of your post (let&rsquo;s call it &ldquo;new-post&rdquo;) create a placeholder: save your original blog post (<code>index.es.md</code>) under the target blog post name (<code>index.en.md</code>) and commit it, then push.</li></ul><figure><img src="placeholder.png"         alt="Diagram with on the left the leaf folder in the new-post branch with the post in Spanish with the text &#39;Hola&#39; and an image; on the right the leaf folder in the new-post branch with the post in Spanish with the text &#39;hola&#39;, the post with the English target filename with the text &#39;hola&#39;, and the image."/></figure><ul><li>Create a new branch, &ldquo;auto-translate&rdquo; for instance.</li><li>Run <code>babeldown::deepl_translate_hugo()</code> with <code>force = TRUE</code>.</li></ul><figure><img src="translate.png"         alt="Diagram with on the left the leaf folder in the auto-translate branch with the post in Spanish with the text &#39;hola&#39;, the post with the English target filename with the text &#39;hola&#39;, and the image; on the right the only thing that changed is that the content of the post with the English target filename is now &#39;hello&#39;."/></figure><ul><li>Commit and push the result.</li><li>Open a PR from the <strong>&ldquo;translation-tech-note&rdquo;</strong> branch to the <strong>&ldquo;new-post&rdquo;</strong> branch.The only difference between the two branches is the automatic translation of your post. The diff for the target blog post will be the diff between the source and target languages! If you have the good habit to start a new line after each sentence / sentence part, it&rsquo;s even better.</li></ul><figure><img src="pr.png"         alt="Drawing of the pull request from the auto-translate to the new-post branch where the difference is that the content of the post with the English target filename has now been translated to English."/></figure><ul><li>The human translators can then a open a second PR to the translation branch with their edits! Or they can add their edits as <a href="https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/commenting-on-a-pull-request#adding-comments-to-a-pull-request">PR suggestions</a>.</li></ul><h3 id="again-in-code">Again: In code</h3><p>Now let&rsquo;s go over this again, but with a coding workflow. Here, we&rsquo;ll use fs and gert (but you do you!), and we&rsquo;ll assume your current directory is the root of the website folder, and also the root of the git repository.</p><ul><li>In the post branch, (again, let&rsquo;s call it &ldquo;new-post&rdquo;), save your original blog post (<code>index.es.md</code>) under the target blog post name (<code>index.en.md</code>) and commit it, then push.</li></ul><div class="highlight"><pre tabindex="0" class="chroma"><code class="language-r" data-lang="r"><span class="line"><span class="cl"><span class="n">fs</span><span class="o">::</span><span class="nf">file_copy</span><span class="p">(</span></span></span><span class="line"><span class="cl">  <span class="nf">file.path</span><span class="p">(</span><span class="s">&#34;content&#34;</span><span class="p">,</span> <span class="s">&#34;blog&#34;</span><span class="p">,</span> <span class="s">&#34;2023-10-01-r-universe-interviews&#34;</span><span class="p">,</span> <span class="s">&#34;index.es.md&#34;</span><span class="p">),</span></span></span><span class="line"><span class="cl">  <span class="nf">file.path</span><span class="p">(</span><span class="s">&#34;content&#34;</span><span class="p">,</span> <span class="s">&#34;blog&#34;</span><span class="p">,</span> <span class="s">&#34;2023-10-01-r-universe-interviews&#34;</span><span class="p">,</span> <span class="s">&#34;index.en.md&#34;</span><span class="p">)</span></span></span><span class="line"><span class="cl"><span class="p">)</span></span></span><span class="line"><span class="cl"><span class="n">gert</span><span class="o">::</span><span class="nf">git_add</span><span class="p">(</span><span class="nf">file.path</span><span class="p">(</span><span class="s">&#34;content&#34;</span><span class="p">,</span> <span class="s">&#34;blog&#34;</span><span class="p">,</span> <span class="s">&#34;2023-10-01-r-universe-interviews&#34;</span><span class="p">,</span> <span class="s">&#34;index.en.md&#34;</span><span class="p">))</span></span></span><span class="line"><span class="cl"><span class="n">gert</span><span class="o">::</span><span class="nf">git_commit</span><span class="p">(</span><span class="s">&#34;Add translation placeholder&#34;</span><span class="p">)</span></span></span><span class="line"><span class="cl"><span class="n">gert</span><span class="o">::</span><span class="nf">git_push</span><span class="p">()</span></span></span></code></pre></div><ul><li>Create a new branch, &ldquo;auto-translate&rdquo; for instance.</li></ul><div class="highlight"><pre tabindex="0" class="chroma"><code class="language-r" data-lang="r"><span class="line"><span class="cl"><span class="n">gert</span><span class="o">::</span><span class="nf">git_branch_create</span><span class="p">(</span><span class="s">&#34;translation-tech-note&#34;</span><span class="p">)</span></span></span></code></pre></div><ul><li>Run <code>babeldown::deepl_translate_hugo()</code> with <code>force = TRUE</code>.</li></ul><div class="highlight"><pre tabindex="0" class="chroma"><code class="language-r" data-lang="r"><span class="line"><span class="cl"><span class="n">babeldown</span><span class="o">::</span><span class="nf">deepl_translate_hugo</span><span class="p">(</span></span></span><span class="line"><span class="cl">  <span class="n">post_path</span> <span class="o">=</span> <span class="nf">file.path</span><span class="p">(</span><span class="s">&#34;content&#34;</span><span class="p">,</span> <span class="s">&#34;blog&#34;</span><span class="p">,</span> <span class="s">&#34;2023-10-01-r-universe-interviews&#34;</span><span class="p">,</span> <span class="s">&#34;index.es.md&#34;</span><span class="p">),</span></span></span><span class="line"><span class="cl">  <span class="n">force</span> <span class="o">=</span> <span class="kc">TRUE</span><span class="p">,</span></span></span><span class="line"><span class="cl">  <span class="n">yaml_fields</span> <span class="o">=</span> <span class="nf">c</span><span class="p">(</span><span class="s">&#34;title&#34;</span><span class="p">,</span> <span class="s">&#34;description&#34;</span><span class="p">,</span> <span class="s">&#34;tags&#34;</span><span class="p">),</span></span></span><span class="line"><span class="cl">  <span class="n">source_lang</span> <span class="o">=</span> <span class="s">&#34;ES&#34;</span><span class="p">,</span></span></span><span class="line"><span class="cl">  <span class="n">target_lang</span> <span class="o">=</span> <span class="s">&#34;EN-US&#34;</span></span></span><span class="line"><span class="cl"><span class="p">)</span></span></span></code></pre></div><p>You can also omit the <code>post_path</code> argument if you&rsquo;re running the code from RStudio IDE and if the open and focused file (the one you see above your console) is the post to be translated.</p><div class="highlight"><pre tabindex="0" class="chroma"><code class="language-r" data-lang="r"><span class="line"><span class="cl"><span class="n">babeldown</span><span class="o">::</span><span class="nf">deepl_translate_hugo</span><span class="p">(</span></span></span><span class="line"><span class="cl">  <span class="n">force</span> <span class="o">=</span> <span class="kc">TRUE</span><span class="p">,</span></span></span><span class="line"><span class="cl">  <span class="n">yaml_fields</span> <span class="o">=</span> <span class="nf">c</span><span class="p">(</span><span class="s">&#34;title&#34;</span><span class="p">,</span> <span class="s">&#34;description&#34;</span><span class="p">,</span> <span class="s">&#34;tags&#34;</span><span class="p">),</span></span></span><span class="line"><span class="cl">  <span class="n">source_lang</span> <span class="o">=</span> <span class="s">&#34;ES&#34;</span><span class="p">,</span></span></span><span class="line"><span class="cl">  <span class="n">target_lang</span> <span class="o">=</span> <span class="s">&#34;EN-US&#34;</span></span></span><span class="line"><span class="cl"><span class="p">)</span></span></span></code></pre></div><ul><li>Commit the result with the code below.</li></ul><div class="highlight"><pre tabindex="0" class="chroma"><code class="language-r" data-lang="r"><span class="line"><span class="cl"><span class="n">gert</span><span class="o">::</span><span class="nf">git_add</span><span class="p">(</span><span class="nf">file.path</span><span class="p">(</span><span class="s">&#34;content&#34;</span><span class="p">,</span> <span class="s">&#34;blog&#34;</span><span class="p">,</span> <span class="s">&#34;2023-10-01-r-universe-interviews&#34;</span><span class="p">,</span> <span class="s">&#34;index.en.md&#34;</span><span class="p">))</span></span></span><span class="line"><span class="cl"><span class="n">gert</span><span class="o">::</span><span class="nf">git_commit</span><span class="p">(</span><span class="s">&#34;Add translation&#34;</span><span class="p">)</span></span></span><span class="line"><span class="cl"><span class="n">gert</span><span class="o">::</span><span class="nf">git_push</span><span class="p">()</span></span></span></code></pre></div><ul><li><p>Open a PR from the <strong>&ldquo;translation-tech-note&rdquo;</strong> branch to the <strong>&ldquo;new-post&rdquo;</strong> branch.The only difference between the two branches is the automatic translation of <code>&quot;content/blog/2023-10-01-r-universe-interviews/index.en.md&quot;</code>.</p></li><li><p>The human translators can then a open a <em>second</em> PR to the translation branch with their edits! Or they can add their edits as <a href="https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/commenting-on-a-pull-request#adding-comments-to-a-pull-request">PR suggestions</a>.</p></li></ul><h3 id="summary-of-branches-and-prs">Summary of branches and PRs</h3><p>In the end there should be two to three branches:</p><ul><li>branch A with blog post in Spanish and placeholder blog post for English (with Spanish content) &ndash; PR to main;</li><li>branch B with blog post automatically translated to English &ndash; PR to branch A;</li><li>Optionally branch C with blog post&rsquo;s English automatic translation edited by a human &ndash; PR to branch B. If branch C does not exist, edits by a human are made as PR review suggestions in the PR from B to A.</li></ul><p>The PR are merged in this order:</p><ul><li>PR to branch B;</li><li>PR to branch A;</li><li>PR to main.</li></ul><h3 id="real-example">Real example</h3><ul><li><a href="https://github.com/ropensci/roweb3/pull/629">PR adding a post to the rOpenSci blog</a>, notice it&rsquo;s a PR from the <strong>&ldquo;r-universe-interviews&rdquo;</strong> branch to the <strong>&ldquo;main&rdquo; (default)</strong> branch;</li><li><a href="https://github.com/ropensci/roweb3/pull/639">PR adding the automatic translation</a>, notice it&rsquo;s a PR to the <strong>&ldquo;r-universe-interviews&rdquo;</strong> branch.</li></ul><figure><img src="pr-diff.png"         alt="Screenshot of the files tab of the pull request adding the automatic translation, where we observe Spanish text in the YAML metadata and Markdown content has been translated to English."/></figure><p>Yanina tweaked the automatic translation by suggesting changes on the PR, then accepting them.</p><figure><img src="pr-comments.png"         alt="Screenshot of the main tab of the pull request adding the automatic translation, where we observe a comment by Yanina replacing the word &#39;article&#39; with &#39;blog post&#39; and fixing the name of &#39;R-universe&#39;."/></figure><h3 id="yaml-fields">YAML fields</h3><p>By default babeldown translates the YAML fields &ldquo;title&rdquo; and &ldquo;description&rdquo;.If you have text in more of them, use the <code>yaml_fields</code> argument of <code>babeldown::deepl_translate_hugo()</code>.</p><p>Note that if babeldown translates the title, it updates the slug.</p><h3 id="glossary">Glossary</h3><p>Imagine you have a few preferences for some words &ndash; something you&rsquo;ll build up over time.</p><div class="highlight"><pre tabindex="0" class="chroma"><code class="language-r" data-lang="r"><span class="line"><span class="cl"><span class="n">readr</span><span class="o">::</span><span class="nf">read_csv</span><span class="p">(</span></span></span><span class="line"><span class="cl">  <span class="nf">system.file</span><span class="p">(</span><span class="s">&#34;example-es-en.csv&#34;</span><span class="p">,</span> <span class="n">package</span> <span class="o">=</span> <span class="s">&#34;babeldown&#34;</span><span class="p">),</span> </span></span><span class="line"><span class="cl">  <span class="n">show_col_types</span> <span class="o">=</span> <span class="kc">FALSE</span></span></span><span class="line"><span class="cl"><span class="p">)</span></span></span></code></pre></div><pre tabindex="0"><code>## # A tibble: 2 × 2##   Spanish     English   ##   &lt;chr&gt;       &lt;chr&gt;     ## 1 paquete     package   ## 2 repositorio repository</code></pre><p>You can record these preferred translations in a glossary in your DeepL account</p><div class="highlight"><pre tabindex="0" class="chroma"><code class="language-r" data-lang="r"><span class="line"><span class="cl"><span class="nf">deepl_upsert_glossary</span><span class="p">(</span></span></span><span class="line"><span class="cl">  <span class="o">&lt;</span><span class="n">path</span><span class="o">-</span><span class="n">to</span><span class="o">-</span><span class="n">csv</span><span class="o">-</span><span class="n">file</span><span class="o">&gt;</span><span class="p">,</span></span></span><span class="line"><span class="cl">  <span class="n">glossary_name</span> <span class="o">=</span> <span class="s">&#34;rstats-glosario&#34;</span><span class="p">,</span></span></span><span class="line"><span class="cl">  <span class="n">target_lang</span> <span class="o">=</span> <span class="s">&#34;Spanish&#34;</span><span class="p">,</span></span></span><span class="line"><span class="cl">  <span class="n">source_lang</span> <span class="o">=</span> <span class="s">&#34;English&#34;</span></span></span><span class="line"><span class="cl"><span class="p">)</span></span></span></code></pre></div><p>You&rsquo;d use the exact same code to <em>update</em> the glossary hence the name &ldquo;upsert&rdquo; for the function.You need one glossary per source language / target language pair: the English-Spanish glossary can&rsquo;t be used for Spanish to English for instance.</p><p>In your <code>babeldown::deepl_translate_hugo()</code> call you then use the glossary name (here &ldquo;rstats-glosario&rdquo;) for the <code>glossary</code> argument.</p><h3 id="formality">Formality</h3><p><code>deepl_translate_hugo()</code> has a <code>formality</code> argument.Now, the DeepL API only supports this for some languages as explained in the <a href="https://www.deepl.com/docs-api/translate-text">documentation of the <code>formality</code> API parameter</a>:</p><blockquote><p>Sets whether the translated text should lean towards formal or informal language. This feature currently only works for target languages DE (German), FR (French), IT (Italian), ES (Spanish), NL (Dutch), PL (Polish), PT-BR and PT-PT (Portuguese), JA (Japanese), and RU (Russian). (&hellip;) Setting this parameter with a target language that does not support formality will fail, unless one of the prefer_&hellip; options are used.</p></blockquote><p>Therefore to be sure a translation will work, instead of writing <code>formality = &quot;less&quot;</code> you can write <code>formality = &quot;prefer_less&quot;</code> which will only use formality if available.</p><h2 id="conclusion">Conclusion</h2><p>In this post we explained how to translate a Hugo blog post using babeldown.Although the gist is to use one call to <code>babeldown::deepl_translate_hugo()</code>,</p><ul><li>one needs to indicate the API URL and key,</li><li>one can improve results by using the function&rsquo;s different arguments,</li><li>we recommend pairing the translation with a Git + GitHub (or GitLab, gitea&hellip;) workflow.</li></ul><p>babeldown has <a href="https://docs.ropensci.org/babeldown/reference/index.html">functions</a> for translating Quarto book chapters, any Markdown file, and any Markdown string, with similar arguments and recommended usage, so explore its reference!</p><p>We&rsquo;d be happy to hear about your <a href="/usecases/">use cases</a>.</p><div class="footnotes" role="doc-endnotes"><hr><ol><li id="fn:1"><p>But you should refer to <a href="https://docs.ropensci.org/tinkr/#loss-of-markdown-style">tinkr docs</a> to see what might change in the Markdown syntax style.&#160;<a href="#fnref:1" class="footnote-backref" role="doc-backlink">&#x21a9;&#xfe0e;</a></p></li><li id="fn:2"><p>adding code to handle Hugo&rsquo;s <a href="https://github.com/r-lib/hugodown/issues/14#issuecomment-632850506">&ldquo;bewildering array of possible config locations&rdquo;</a> and two possible formats (YAML and TOML) is out of scope for babeldown at this point.&#160;<a href="#fnref:2" class="footnote-backref" role="doc-backlink">&#x21a9;&#xfe0e;</a></p></li></ol></div>',
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
    assert result[0] == {"doi": "https://doi.org/10.53731/ar11b-5ea39", "key": "ref1"}


# def test_get_title():
#     """Sanitize title with spaces."""
#     title = "  <h2>Bla</h2/><i>bla</i>"
#     result = get_title(title)
#     assert result == "<strong>Bla</strong><i>bla</i>"


def test_get_abstract():
    """Sanitize and truncate abstract."""
    abstract = """
    There’s something special about language. It is ‘our own’, it is ‘us’, in a profound way, and quite surprisingly, more so than art. I was deeply struck by this when I first saw reactions to large generative language models that created realistic, human-ish prose. Notably, those mature enough to reach a non-professional audience – ChatGPT based on GPT-3 and later GPT-4 – came quite some time after models that could create fairly acceptable visual ‘art’.1 The appearance of synthetic language-like products (SLLPs), as I like to call the output of such generative models, came well after the appearance of synthetic simulacra of visual art,2 yet elicited much less fervent responses."""
    result = get_abstract(abstract)
    assert len(result) <= 450
    assert result.endswith("Notably,")
