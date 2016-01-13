$.ajaxSetup({
  beforeSend: function(xhr, settings) {
    if (!/^(GET|HEAD|OPTIONS|TRACE)$/i.test(settings.type) && !this.crossDomain) {
      xhr.setRequestHeader("X-CSRFToken", csrftoken);
    }
  }
})

var baseURL = document.location.origin;

var SuccessAlert = React.createClass({
  render: function() {
    return (
      <div className="row alert-row">
        <div className="col-md-12">
          <div className="alert alert-success fade in hidden" role="alert">
            Invite successfully sent.
          </div>
        </div>
      </div>
    );
  }
});

var LinkList = React.createClass({
  handleDelete: function(uri, e) {
    e.preventDefault();
    this.props.onLinkDelete({uri: uri});
  },
  render: function() {
    var createItem = function(container, link) {
      var onDelete = container.handleDelete.bind(container, link.uri);
      return (
        <div className="row">
          <div className="col-sm-6 col-xs-12">
            <a href={link.public_uri}>{link.public_uri}</a>
          </div>
          <div className="col-sm-6 col-xs-12">
            {link.giver}
            <button type="button" className="close" onClick={onDelete}>
              <span aria-hidden="true">&times;</span>
              <span className="sr-only visible-xs">Close</span>
            </button>
          </div>
        </div>
      );
    };

    var links = [];
    for (var i = 0; i < this.props.links.length; i++) {
      links.push(createItem(this, this.props.links[i]));
    }

    return (
      <div>
        <hr/>
        <div className="row">
          <div className="col-md-12">
            <div className="link-table">
              <h2>Pending file requests</h2>
              <div className="row table-header hidden-xs">
                <div className="col-sm-6">
                  Link
                </div>
                <div className="col-sm-6">
                  Email sent to
                </div>
              </div>
              {links}
            </div>
          </div>
        </div>
      </div>
    );
  }
});

var LinkMaker = React.createClass({
  handleLinkRequest: function(e) {
    e.preventDefault();
    this.props.onLinkSubmit({});
    return;
  },
  render: function() {
    return (
      <form id="link-maker" role="form" method="POST" onSubmit={this.handleLinkRequest}>
        <button className="btn btn-primary btn-lg btn-xl gold-button">Request file</button>
        <p className="help-block">
          This will generate a link to a webpage where the link's recipient can upload a file to your AeroFS folder.
        </p>
      </form>
    );
  }
});

var InviteMaker = React.createClass({
  handleEmail: function(e) {
    e.preventDefault();
    var email = this.refs.email.getDOMNode().value.trim();
    var message = this.refs.message.getDOMNode().value.trim();
    this.props.onInviteSubmit({email: email, message: message, link: this.props.newLink});
    return;
  },
  doneWithLink: function(e){
    e.preventDefault();
    this.props.onDoneWithLink();
  },
  defaultInviteText: 'Hi! There is a file you have that I would like you to share with me. ' +
    'Please click the link below to upload the file to my AeroFS folder via AeroUP. ',
  render: function() {
    return (
      <div id="invite-maker">
        <form role="form" method="POST" onSubmit={this.doneWithLink}>
          <h3>Copy and paste link</h3>
          <p className="link">{ baseURL + this.props.newLink.public_uri }</p>
          <p className="help-block">The person you give this link to will be able to upload one file to your AeroFS folder.</p>
          <div className="form-group">
            <input type="submit" className="btn btn-default pull-right" value="Done with this link"></input>
          </div>
        </form>
        <div className="clearfix"></div>
        <h4 className="text-center">-or-</h4>
        <form role="form" method="POST" onSubmit={this.handleEmail}>
          <div className="form-group">
            <h3>Send link via email</h3>
            <label htmlFor="email" className="control-label sr-only">Email</label>
            <input type="email" id="email" name="email" ref="email" className="form-control" placeholder="Email address"></input>
          </div>
          <div className="form-group">
            <label htmlFor="request-text" className="control-label">File request text (optional)</label>
            <textarea id="request-text" name="request-text" ref="message" className="form-control">{this.defaultInviteText}</textarea>
          </div>
          <div className="form-group">
            <input type="submit" className="btn btn-primary pull-right" value="Send email"></input>
          </div>
        </form>
      </div>
    );
  }
});'

var Dashboard = React.createClass({
  getInitialState: function() {
    var state = this.getDefaultState();
    state.links = [];
    return state;
  },
  getDefaultState: function() {
    return {
      linkGenerated: false,
      newLink: {
        uri: null,
        public_uri: null,
        expiry_date: null,
        giver: null,
        receiver: null
      }
    }
  },
  setDefaultState: function() {
    this.setState(this.getDefaultState());
  },
  loadLinkData: function(){
    $.ajax({
      url: this.props.url,
      dataType: 'json',
      success: function(data) {
        this.setState({links: data});
      }.bind(this),
      error: function(xhr, status, err) {
        console.error(this.props.url, status, err.toString());
      }.bind(this)
    });
  },
  componentDidMount: function() {
    this.loadLinkData();
    // for polling
    setInterval(this.loadLinkData, this.props.pollInterval);
    },
  handleLinkSubmit: function(e){
    $.ajax({
      url: this.props.url,
      dataType: 'json',
      type: 'POST',
      success: function(data) {
        this.setState({linkGenerated: true, newLink: data});
        var newLinks = this.state.links.concat([this.state.newLink]);
        this.setState({links: newLinks});
      }.bind(this),
      error: function(xhr, status, err) {
        console.error(this.props.url, status, err.toString());
      }.bind(this)
    });
  },
  handleInviteSubmit: function(data) {
    var hideAlert = function() {
      $($('.alert')[0]).addClass('hidden');
    };

    // TODO: get email invite API call working
    $.ajax({
      url: data.link.uri,
      dataType: 'json',
      contentType: 'application/json; charset=utf-8',
      type: 'POST',
      data: JSON.stringify({
        giver: data.email,
        message: data.message
      }),
      success: function() {
        // add giver email address to link
        var newLinks = this.state.links;
        for (var i = 0; i < this.state.links.length; i++) {
          if (this.state.links[i].uri === data.link.uri) {
            newLinks[i].giver = data.email;
            this.setState({links: newLinks});
          }
        }

        // reset state so another link can be created if desired
        this.setDefaultState();
        $('html, body').animate({ scrollTop: 0 }, 'fast');
        $($('.alert')[0]).removeClass('hidden');
        window.setTimeout(hideAlert, 6000);
      }.bind(this),
      error: function(xhr, status, err) {
        console.error(this.props.url, status, err.toString());
      }.bind(this)
    });
  },
  handleLinkDelete: function(link) {
    var updatedLinks = this.state.links;
    for (var i = 0; i < this.state.links.length; i++) {
      if (this.state.links[i].uri === link.uri) {
        $.ajax({
          url: this.state.links[i].uri,
          dataType: 'json',
          type: 'DELETE',
          success: function() {
            updatedLinks.splice(i,1);
            this.setState({links: updatedLinks});
          }.bind(this),
          error: function(xhr, status, err) {
            console.error(this.props.url, status, err.toString());
          }.bind(this)
        });
        break;
      }
    }
  },
  render: function() {
    return (
      <div>
        <SuccessAlert />
        <div className="row">
          <div className="col-md-12">
            { this.state.linkGenerated ? null : <LinkMaker onLinkSubmit={this.handleLinkSubmit} /> }
            { this.state.linkGenerated ? <InviteMaker newLink={this.state.newLink} onInviteSubmit={this.handleInviteSubmit} onDoneWithLink={this.setDefaultState}/> : null }
          </div>
        </div>
        { this.state.links.length > 0 ? <LinkList links={this.state.links} onLinkDelete={this.handleLinkDelete}/> : null }
      </div>
    );
  }
});

React.render(<Dashboard url="/links" pollInterval={15000} />, document.getElementById('dashboard'));
